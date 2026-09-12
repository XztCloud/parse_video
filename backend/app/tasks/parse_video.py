import os, json
import threading

from pydantic import BaseModel
from app.services.clone import begin_clone
from app.celery_app import celery_app
from app.database import SessionLocal
from app.models.video import Video, VideoStatus
from app.models.script import Script, ScriptSegment, SegmentType
from app.services.video_processor import VideoProcessor
from app.services.asr_service import ASRService
from app.services.visual_service import VisualService
from app.services.script_generator import ScriptGenerator, extract_shot_features
from celery.signals import worker_process_init, worker_process_shutdown

from app.util import ImageRegenerateInput
from app.services.clone_image import regenerate_image
from app.services.clone_frame import regenerate_segment_frame
from ..config import settings

from celery.utils.log import get_task_logger
from app.tasks.process_loop_manager import process_loop


logger = get_task_logger(__name__)


@worker_process_init.connect
def on_worker_init(*args, **kwargs):
    """当 Celery fork 出 Worker 子进程后，在此子进程内初始化唯一的 Loop 和 DB 连接池
    """
    process_loop.init_process()

@worker_process_shutdown.connect
def on_worker_shutdown(*args, **kwargs):
    """销毁进程中loop关联链接
    """
    process_loop.shutdown()
    


@celery_app.task(bind=True)
def parse_video_task(self, video_id: int):
    db = SessionLocal()
    try:
        logger.info('start celery task: parse_video_task')
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise ValueError(f"Video {video_id} not found")
        video.status = VideoStatus.PROCESSING
        video.progress = 0
        # 记录视频时长（get_duration 返回秒数）
        try:
            video.duration = VideoProcessor.get_duration(video.file_path)
        except Exception:
            logger.exception('failed to get video duration, keep None')
        db.commit()
        
        audio_path = VideoProcessor.extract_audio(video.file_path)
        video.progress = 20
        db.commit()

        # 新增 Scene Detect
        scene_info_list = VideoProcessor.split_video_into_scenes(video_path=video.file_path, output_dir=settings.UPLOAD_DIR + f'/{video.id}')
        if len(scene_info_list) == 0:
            video.status = VideoStatus.FAILED
            video.error_message = 'split_video_into_scenes failed.'
            db.commit()
            raise ValueError("split_video_into_scenes returned empty list")

        video.progress = 30
        db.commit()
        trans_ret = ASRService.transcribe(audio_path)
        if trans_ret is None:
            video.status = VideoStatus.FAILED
            video.error_message = "not find audio track."
            db.commit()
            raise ValueError("ASR transcription returned None")
        asr_segments, all_text= trans_ret

        video.progress = 60
        logger.info(f'asr_segments: {asr_segments}')
        db.commit()
        visual_segments = process_loop.run(VisualService.analyze_frames(scene_info_list, fps=1.0))
        if visual_segments is None:
            video.status = VideoStatus.FAILED
            video.error_message = "visual analyze frames failed."
            db.commit()
            raise ValueError("visual analyze frames returned None")

        logger.info(f'visual_segments: {visual_segments}')
        video.progress = 80
        db.commit()

        script_result = process_loop.run(ScriptGenerator.generate_script(asr_segments, visual_segments))
        logger.info(f'script_result: {script_result}')

        # 增强分镜描述：结合画面描述和对话生成更完整的 shot_description
        script_result = process_loop.run(ScriptGenerator.enhance_shot_descriptions(script_result))
        logger.info(f'enhanced script_result: {script_result}')

        parse_result = process_loop.run(ScriptGenerator.summary_script(script_result=script_result, output_dir=settings.UPLOAD_DIR + f'/{video.id}'))
        logger.info(f'parse_result: {parse_result}')
        video.progress = 95
        db.commit()

        for idx, ret in enumerate(parse_result):
            logger.info(f'ret[{idx}] is {ret}')

        script = Script(video_id=video.id, content=script_result, raw_asr_text=json.dumps(asr_segments, ensure_ascii=False), 
                        raw_visual_text=json.dumps(visual_segments, ensure_ascii=False), parse_pointer=parse_result[0], 
                        parse_script=parse_result[1], parse_file_path=parse_result[3])
        db.add(script)
        db.flush()

        # LLM 批量生成每个分镜的镜头特征标签（一次调用），失败回退关键词
        try:
            shot_feats = process_loop.run(ScriptGenerator.generate_shot_features(script_result))
        except Exception:
            logger.exception('generate_shot_features failed, fallback to keyword extract')
            shot_feats = []

        for idx, seg in enumerate(script_result):
            logger.info(f'seg: {seg}, seg type: {type(seg)}')
            # 优先使用 LLM 标签，LLM 结果缺失或为空时回退到关键词提取
            features = (
                shot_feats[idx]
                if idx < len(shot_feats) and isinstance(shot_feats[idx], list) and shot_feats[idx]
                else extract_shot_features(seg.get("shot_description", ""))
            )
            segment = ScriptSegment(script_id=script.id, start_time=seg.get("start_time", 0), end_time=seg.get("end_time", 0), shot_description=seg.get("shot_description", ""), dialogue=seg.get("dialogue", ""), shot_features=features, segment_type=SegmentType(seg.get("segment_type", "mixed")))
            db.add(segment)

        # 视频类型总结（失败不阻塞主流程，落回未知分类）
        try:
            type_result = process_loop.run(
                ScriptGenerator.summary_video_type(json.dumps(script_result, ensure_ascii=False))
            )
        except Exception:
            logger.exception('summary_video_type failed')
            type_result = {"category": "未知分类", "summary": ""}
        video.category = type_result.get("category") or "未知分类"
        video.type_summary = type_result.get("summary") or ""
        video.status = VideoStatus.DONE
        video.progress = 100
        db.commit()
    except Exception as e:
        try:
            video = db.query(Video).filter(Video.id == video_id).first()
            if video:
                video.status = VideoStatus.FAILED
                video.error_message = str(e)
                db.commit()
        except Exception:
            logger.exception('Failed to update video status to FAILED')
        raise
    finally:
        db.close()


@celery_app.task(bind=True)
def clone_video_task(self, clone_script_id: int, step: int=1, auto_run: bool=False, stop_step: int=8) -> any:
    """复刻视频worker

    Args:
        clone_script_id (int): 复刻信息id
        step (int, optional): 执行步骤 plot voice segments image video. Defaults to 1.
        auto_run (bool, optional): 是否自动执行下一步. Defaults to False.
        stop_step (int, optional): 自动执行到该阶段为止（含）；默认 8=全流程，
            复刻剧本只跑到分镜则传 2（end 于 SEGMENTS_DONE）。Defaults to 8.

    Returns:
        any: worker返回结果
    """
    return process_loop.run(begin_clone(clone_script_id, step=step, auto_run=auto_run, stop_step=stop_step))

@celery_app.task(bind=True)
def regenerate_task(self, category: str, id: int, payload: dict):

    main_category, detail_category = category.split('.')
    logger.info(f'receive regenerate image msg:{main_category} - {detail_category}')
    if main_category == 'image':
        if detail_category in ['role', 'scene']:
            process_loop.run(regenerate_image(detail_category, id, payload))
        else:
            process_loop.run(regenerate_segment_frame(id, payload))


@celery_app.task(bind=True)
def novel_generate_task(self, novel_id: int, theme: str, requirements: dict | None = None, auto_run: bool = False):
    """小说转剧本Celery任务

    Args:
        novel_id: 小说ID
        theme: 主题
        requirements: 额外要求
        auto_run: 是否自动运行下游pipeline

    Returns:
        创建的CloneScript ID列表
    """
    from app.services.novel_script_generator import generate_novel_scripts

    try:
        logger.info(f'Starting novel_generate_task for novel_id={novel_id}')
        result = process_loop.run(
            generate_novel_scripts(novel_id, theme, requirements, auto_run)
        )
        logger.info(f'novel_generate_task completed, created {len(result)} CloneScripts')
        return result
    except Exception as e:
        logger.exception(f'novel_generate_task failed: {e}')
        raise
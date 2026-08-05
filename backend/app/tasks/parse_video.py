import os, json, asyncio
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
from app.services.script_generator import ScriptGenerator
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
            raise
        video.status = VideoStatus.PROCESSING
        video.progress = 0
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
            raise

        video.progress = 30
        db.commit()
        trans_ret = ASRService.transcribe(audio_path)
        if trans_ret is None:
            video.status = VideoStatus.FAILED
            video.error_message = "not find audio track."
            db.commit()
            raise
        asr_segments, all_text= trans_ret

        video.progress = 60
        logger.info(f'asr_segments: {asr_segments}')
        db.commit()
        logger.info('0')
        visual_segments = asyncio.run(VisualService.analyze_frames(scene_info_list, fps=1.0))
        if visual_segments is None:
            video.status = VideoStatus.FAILED
            video.error_message = "visual analyze frames failed."
            db.commit()
            raise ValueError("visual analyze frames returned None")

        logger.info(f'visual_segments: {visual_segments}')
        video.progress = 80
        db.commit()

        script_result = asyncio.run(ScriptGenerator.generate_script(asr_segments, visual_segments))
        logger.info(f'script_result: {script_result}')

        parse_result = asyncio.run(ScriptGenerator.summary_script(script_result=script_result, output_dir=settings.UPLOAD_DIR + f'/{video.id}'))
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

        for seg in script_result:
            logger.info(f'seg: {seg}, seg type: {type(seg)}')
            segment = ScriptSegment(script_id=script.id, start_time=seg.get("start_time", 0), end_time=seg.get("end_time", 0), shot_description=seg.get("shot_description", ""), dialogue=seg.get("dialogue", ""), segment_type=SegmentType(seg.get("segment_type", "mixed")))
            db.add(segment)
        video.status = VideoStatus.DONE
        video.progress = 100
        db.commit()
    except Exception as e:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = VideoStatus.FAILED
            video.error_message = str(e)
            db.commit()
        raise
    finally:
        db.close()


@celery_app.task(bind=True)
def clone_video_task(self, clone_script_id: int, step: int=1, auto_run: bool=False) -> any:
    """复刻视频worker

    Args:
        clone_script_id (int): 复刻信息id
        step (int, optional): 执行步骤 plot voice segments image video. Defaults to 1.
        auto_run (bool, optional): 是否自动执行下一步. Defaults to False.

    Returns:
        any: worker返回结果
    """
    return process_loop.run(begin_clone(clone_script_id, step=step, auto_run=auto_run))

@celery_app.task(bind=True)
def regenerate_task(self, category: str, id: int, payload: dict):
    
    main_category, detail_category = category.split('.')
    logger.info(f'receive regenerate image msg:{main_category} - {detail_category}')
    if main_category == 'image':
        if detail_category in ['role', 'scene']:
            process_loop.run(regenerate_image(detail_category, id, payload))
        else:
            process_loop.run(regenerate_segment_frame(id, payload))
            
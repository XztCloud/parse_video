import os, json, asyncio
from celery_app import celery_app
from app.database import SessionLocal
from app.models.video import Video, VideoStatus
from app.models.script import Script, ScriptSegment, SegmentType
from app.services.video_processor import VideoProcessor
from app.services.asr_service import ASRService
from app.services.visual_service import VisualService
from app.services.script_generator import ScriptGenerator
from ..config import settings

@celery_app.task(bind=True)
def parse_video_task(self, video_id: int):
    db = SessionLocal()
    try:
        print('start celery task: parse_video_task')
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            return
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
            video.error_message = str(e)
            db.commit()
            raise
        asr_segments, all_text= trans_ret

        video.progress = 60
        print(f'asr_segments: {asr_segments}')
        db.commit()
        print('0')
        visual_segments = asyncio.run(VisualService.analyze_frames(scene_info_list, fps=1.0))
        if visual_segments is None:
            video.status = VideoStatus.FAILED
            video.error_message = str(e)
            db.commit()
            raise

        print(f'visual_segments: {visual_segments}')
        video.progress = 80
        db.commit()

        script_result = asyncio.run(ScriptGenerator.llm_generate_script(asr_segments, visual_segments))
        print(f'script_result: {script_result}')

        parse_result = asyncio.run(ScriptGenerator.summary_script(script_result=script_result, output_dir=settings.UPLOAD_DIR + f'/{video.id}'))
        print(f'parse_result: {parse_result}')
        video.progress = 95
        db.commit()

        for idx, ret in enumerate(parse_result):
            print(f'ret[{idx}] is {ret}')

        script = Script(video_id=video.id, content=script_result, raw_asr_text=json.dumps(asr_segments, ensure_ascii=False), 
                        raw_visual_text=json.dumps(visual_segments, ensure_ascii=False), parse_pointer=parse_result[0], 
                        parse_script=parse_result[1], parse_file_path=parse_result[2])
        db.add(script)
        db.flush()

        for seg in script_result:
            print(f'seg: {seg}, seg type: {type(seg)}')
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
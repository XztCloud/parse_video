from multiprocessing import Semaphore
import asyncio
import os, uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel

from app.api.deps import SessionDep
from ...database import SessionLocal
from ...models.video import Video, VideoStatus, VideoSource
from ...config import settings
from ...tasks.parse_video import parse_video_task
from ...services.douyin_parser import DouyinParser
from app.util import logger

router = APIRouter(prefix="/videos", tags=["videos"])

class DouyinRequest(BaseModel):
    url: str

# 单机多进程
MAX_CONCURRENT = 5
# 初始化一个跨进程的信号量
process_semaphore = Semaphore(MAX_CONCURRENT)

def acquire_lock():
    # 这是一个阻塞操作，必须在独立线程中运行，否则会卡死 asyncio 事件循环
    process_semaphore.acquire()

def release_lock():
    process_semaphore.release()

@router.post("/upload")
async def upload_video(db: SessionDep, file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
        raise HTTPException(status_code=400, detail="不支持的视频格式")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    abs_file_path = os.path.abspath(file_path)
    print(f'abs_file_path:{abs_file_path}')
    try:
        video = Video(title=file.filename, file_path=abs_file_path, status=VideoStatus.PENDING, progress=0)
        db.add(video)
        db.commit()
        db.refresh(video)
        parse_video_task.delay(video.id)
        return {"id": video.id, "filename": video.title, "status": video.status.value, "progress": video.progress}
    except Exception as e:
        logger.exception(f'upload file failed. {str(e)}')
        raise HTTPException(status_code=400, detail=f"上传文件失败: {str(e)}")


@router.post("/douyin")
async def parse_douyin(request: DouyinRequest, db: SessionDep):
    await asyncio.to_thread(acquire_lock)
    try:
        print(f'receive url:{request.url}')
        file_path, title = await asyncio.to_thread(DouyinParser.download_video, request.url)
        print(f'file_path:{file_path}, title:{title}')

        video = Video(
            title=title,
            file_path=file_path,
            status=VideoStatus.PENDING,
            progress=0,
            source_type=VideoSource.DOUYIN,
            source_url=request.url
        )
        db.add(video)
        db.commit()
        db.refresh(video)
        parse_video_task.delay(video.id)
        return {"id": video.id, "filename": video.title, "status": video.status.value, "progress": video.progress}

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"抖音链接解析失败: {str(e)}")
    finally:
        await asyncio.to_thread(release_lock)

@router.get("")
async def list_videos(db: SessionDep, skip: int = 0, limit: int = 20):
    try:
        videos = db.query(Video).order_by(Video.created_at.desc()).offset(skip).limit(limit).all()
        return [
            {
                "id": v.id,
                "filename": v.title,
                "status": v.status.value,
                "progress": v.progress,
                "error_message": v.error_message
            }
            for v in videos
        ]
    except Exception as e:
        logger.exception(f'list_videos failed. ')
        raise HTTPException(status_code=400, detail=f"获取视频列表失败: {str(e)}")

@router.get("/{video_id}/status")
async def get_video_status(video_id: int, db: SessionDep):

    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="视频不存在")
        return {
            "id": video.id, 
            "filename": video.title, 
            "status": video.status.value, 
            "progress": video.progress,
            "error_message": video.error_message}
    except Exception as e:
        logger.exception(f'get_video_status failed. ')
        raise HTTPException(status_code=400, detail=f"获取视频{video_id}状态失败: {str(e)}")
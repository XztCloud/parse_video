import os, uuid
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from ..database import SessionLocal
from ..models.video import Video, VideoStatus, VideoSource
from ..config import settings
from ..tasks.parse_video import parse_video_task
from ..services.douyin_parser import DouyinParser

router = APIRouter(prefix="/videos", tags=["videos"])

class DouyinRequest(BaseModel):
    url: str

@router.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    if not file.filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
        raise HTTPException(status_code=400, detail="不支持的视频格式")
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename)[1]
    filename = f"{uuid.uuid4()}{ext}"
    file_path = os.path.join(settings.UPLOAD_DIR, filename)
    with open(file_path, "wb") as f:
        f.write(await file.read())
    db = SessionLocal()
    abs_file_path = os.path.abspath(file_path)
    print(f'abs_file_path:{abs_file_path}')
    try:
        video = Video(title=file.filename, file_path=abs_file_path, status=VideoStatus.PENDING, progress=0)
        db.add(video)
        db.commit()
        db.refresh(video)
        parse_video_task.delay(video.id)
        return {"id": video.id, "filename": video.title, "status": video.status.value, "progress": video.progress}
    finally:
        db.close()

@router.post("/douyin")
async def parse_douyin(request: DouyinRequest):
    try:
        file_path, title = DouyinParser.download_video(request.url)
        print(f'file_path:{file_path}, title:{title}')
        db = SessionLocal()
        try:
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
        finally:
            db.close()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"抖音链接解析失败: {str(e)}")

@router.get("/")
async def list_videos(skip: int = 0, limit: int = 20):
    db = SessionLocal()
    try:
        videos = db.query(Video).order_by(Video.created_at.desc()).offset(skip).limit(limit).all()
        return [
            {
                "id": v.id,
                "filename": v.title,
                "status": v.status.value,
                "progress": v.progress,
                "clone_status": v.clone_status.value,
                "clone_progress": v.clone_progress,
                "error_message": v.error_message
            }
            for v in videos
        ]
    finally:
        db.close()

@router.get("/{video_id}/status")
async def get_video_status(video_id: int):
    db = SessionLocal()
    try:
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise HTTPException(status_code=404, detail="视频不存在")
        return {"id": video.id, "filename": video.title, "status": video.status.value, "progress": video.progress, "error_message": video.error_message}
    finally:
        db.close()
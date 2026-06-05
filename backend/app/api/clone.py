

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.database import SessionLocal
from app.models.script import CloneScript, Script
from app.models.video import CloneStatus, Video
from app.tasks.parse_video import clone_video_task


class CloneRequest(BaseModel):
    video_id: int =  Field(..., alias="videoId") 
    theme: str

router = APIRouter(prefix="/clone", tags=["clone"])


@router.post("/video")
async def clone_video(request: CloneRequest):
    try:
        print('receive clone_video post.')
        db = SessionLocal()
        try:
            video = db.query(Video).filter(Video.id == request.video_id).first()
            if not video:
                raise HTTPException(status_code=404, detail="视频信息不存在")
            
            video.clone_progress = 0
            video.clone_status = CloneStatus.CLONING
            db.commit()

            clone_video_task.delay(video.id, request.theme)
            return {"id": video.id, "theme": request.theme, "status": video.clone_status, "progress": video.clone_progress}
        except Exception as e:
            video.clone_status = CloneStatus.CLONE_FAILED
            db.commit()
        finally:
            db.close()
    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")
    

@router.get("/{video_id}/status")
async def get_clone_status(video_id: int):
    pass

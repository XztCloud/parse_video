"""视频业务逻辑层：负责视频记录创建、查询，与路由层解耦。"""
from datetime import datetime, timezone, timedelta
import uuid
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.video import Video, VideoStatus, VideoSource
from app.services.ownership import scope_by_owner

# 北京时间 UTC+8
BJ_TZ = timezone(timedelta(hours=8))


async def create_video_record(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    title: str,
    file_path: str,
    source_type: VideoSource = VideoSource.LOCAL,
    source_url: str | None = None,
) -> Video:
    """创建 Video 记录并提交（user_id 为归属用户）。"""
    video = Video(
        title=title,
        file_path=file_path,
        status=VideoStatus.PENDING,
        progress=0,
        source_type=source_type,
        source_url=source_url,
        user_id=user_id,
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)
    return video


def video_to_dict(video: Video) -> dict:
    """Video ORM 对象转为前端友好的 dict。"""
    return {
        "id": video.id,
        "filename": video.title,
        "status": video.status.value,
        "progress": video.progress,
        "error_message": video.error_message,
        "duration": video.duration,
        "category": video.category,
        "type_summary": video.type_summary,
        "created_at": video.created_at.replace(tzinfo=timezone.utc).astimezone(BJ_TZ).isoformat() if video.created_at else None,
    }


async def get_video_by_id(db: AsyncSession, video_id: int) -> Video | None:
    result = await db.execute(select(Video).where(Video.id == video_id))
    return result.scalar_one_or_none()


async def list_videos(db: AsyncSession, user: User, skip: int = 0, limit: int = 20) -> list[Video]:
    """列出当前用户可见的视频（超管可见全部）。"""
    stmt = select(Video).order_by(Video.created_at.desc())
    stmt = scope_by_owner(stmt, Video, user)
    result = await db.execute(stmt.offset(skip).limit(limit))
    return list(result.scalars().all())

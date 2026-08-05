"""视频业务逻辑层：负责视频记录创建、查询，与路由层解耦。"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video import Video, VideoStatus, VideoSource


async def create_video_record(
    db: AsyncSession,
    *,
    title: str,
    file_path: str,
    source_type: VideoSource = VideoSource.LOCAL,
    source_url: str | None = None,
) -> Video:
    """创建 Video 记录并提交。"""
    video = Video(
        title=title,
        file_path=file_path,
        status=VideoStatus.PENDING,
        progress=0,
        source_type=source_type,
        source_url=source_url,
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
    }


async def get_video_by_id(db: AsyncSession, video_id: int) -> Video | None:
    result = await db.execute(select(Video).where(Video.id == video_id))
    return result.scalar_one_or_none()


async def list_videos(db: AsyncSession, skip: int = 0, limit: int = 20) -> list[Video]:
    result = await db.execute(
        select(Video).order_by(Video.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())

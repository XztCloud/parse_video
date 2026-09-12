"""资产归属校验。

归属只落在最外层的 videos / novels 两张表（user_id）；其余资产（scripts、clone_scripts
及其所有子表）的归属通过 script→video 或 novel 推导。

约定：
- 超管（is_superuser=True）不受限制，可访问全部资产；
- 普通用户仅能访问自己名下的资产；
- 读接口无权一律按「不存在」返回（404），避免通过 id 探测他人资产是否存在。
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.models.novel import Novel
from app.models.script import CloneScript, CloneScriptSegment, Script
from app.models.user import User
from app.models.video import Video


def is_owner_or_superuser(user: User, owner_id) -> bool:
    """超管恒为 True；普通用户需 owner_id 与本人一致（None 视为无权）。"""
    if user is None:
        return False
    if user.is_superuser:
        return True
    return owner_id is not None and owner_id == user.id


def scope_by_owner(stmt: Select, model, user: User) -> Select:
    """给查询追加归属过滤：超管不过滤，普通用户仅限本人。"""
    if user is None:
        return stmt.where(model.user_id.is_(None))  # 兜底：无用户时不给任何数据
    if user.is_superuser:
        return stmt
    return stmt.where(model.user_id == user.id)


async def get_owned_video(db: AsyncSession, video_id: int, user: User) -> Video | None:
    video = (await db.execute(select(Video).where(Video.id == video_id))).scalar_one_or_none()
    if not video or not is_owner_or_superuser(user, video.user_id):
        return None
    return video


async def get_owned_novel(db: AsyncSession, novel_id: int, user: User) -> Novel | None:
    novel = (await db.execute(select(Novel).where(Novel.id == novel_id))).scalar_one_or_none()
    if not novel or not is_owner_or_superuser(user, novel.user_id):
        return None
    return novel


async def _get_owned_script(db: AsyncSession, condition, user: User) -> Script | None:
    stmt = (
        select(Script, Video.user_id)
        .join(Video, Script.video_id == Video.id)
        .where(condition)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        return None
    script, owner_id = row[0], row[1]
    return script if is_owner_or_superuser(user, owner_id) else None


async def get_owned_script_by_video(db: AsyncSession, video_id: int, user: User) -> Script | None:
    """按 video_id 取解析脚本，并校验其所属视频的归属。"""
    return await _get_owned_script(db, Script.video_id == video_id, user)


async def get_owned_script_by_id(db: AsyncSession, script_id: int, user: User) -> Script | None:
    """按 script_id 取解析脚本，并校验其所属视频的归属。"""
    return await _get_owned_script(db, Script.id == script_id, user)


async def assert_clone_script_access(db: AsyncSession, clone_script_id: int, user: User) -> CloneScript:
    """取复刻脚本并校验归属（经 script→video 或 novel 推导），无权抛 404。"""
    stmt = (
        select(
            CloneScript,
            Video.user_id.label("video_owner"),
            Novel.user_id.label("novel_owner"),
        )
        .outerjoin(Script, CloneScript.script_id == Script.id)
        .outerjoin(Video, Script.video_id == Video.id)
        .outerjoin(Novel, CloneScript.novel_id == Novel.id)
        .where(CloneScript.id == clone_script_id)
    )
    row = (await db.execute(stmt)).first()
    if not row:
        raise HTTPException(status_code=404, detail="复刻视频脚本不存在")
    clone_script, video_owner, novel_owner = row[0], row[1], row[2]
    if not is_owner_or_superuser(user, video_owner or novel_owner):
        raise HTTPException(status_code=404, detail="复刻视频脚本不存在")
    return clone_script


async def assert_segment_image_access(db: AsyncSession, image, user: User) -> None:
    """分镜首帧（clone_segment_images）的归属，由其所在分镜所属的复刻脚本推导。"""
    segment = (
        await db.execute(
            select(CloneScriptSegment).where(CloneScriptSegment.id == image.clone_script_sgement_id)
        )
    ).scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="图片记录不存在")
    await assert_clone_script_access(db, segment.script_id, user)


async def assert_segment_video_access(db: AsyncSession, seg_video, user: User) -> None:
    """分镜视频（clone_segment_video）的归属，由其所在分镜所属的复刻脚本推导。"""
    segment = (
        await db.execute(
            select(CloneScriptSegment).where(CloneScriptSegment.id == seg_video.clone_script_sgement_id)
        )
    ).scalar_one_or_none()
    if not segment:
        raise HTTPException(status_code=404, detail="视频记录不存在")
    await assert_clone_script_access(db, segment.script_id, user)


async def assert_image_access(db: AsyncSession, category: str, image, user: User) -> None:
    """图片类资源（role/scene/frame）的归属校验统一入口。"""
    if category == "frame":
        await assert_segment_image_access(db, image, user)
    else:
        await assert_clone_script_access(db, image.script_id, user)

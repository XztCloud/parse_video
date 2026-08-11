"""复刻业务逻辑层：负责 CloneScript 各阶段的状态流转与详情组装，与路由层解耦。

阶段 step 映射（与 LangGraph clone.py 的 step 对应）：
    1 = plot（剧本）   2 = voice（配音）   3 = segments（分镜）
    4 = images（生图）  5 = frames（参考帧） 6 = segment_videos（分镜视频）
    7 = video（合并成片）
"""
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.script import (
    CloneRoleImage,
    CloneSceneImage,
    CloneSegmentImg,
    CloneSegmentVideo,
    CloneVoice,
    CloneScript,
    CloneScriptSegment,
    CloneVideo,
    CloneStatus,
)


# step -> (进入状态, 进度, 前置允许状态列表)
_CLONE_STEP_CONFIG = {
    2: (CloneStatus.VOICE, 21, [CloneStatus.PLOT_DONE, CloneStatus.VOICE_DONE]),
    3: (CloneStatus.SEGMENTS, 31, [CloneStatus.PLOT_DONE, CloneStatus.VOICE_DONE, CloneStatus.SEGMENTS_DONE]),
    4: (CloneStatus.IMAGE, 31, [CloneStatus.SEGMENTS_DONE, CloneStatus.IMAGE_DONE]),
    5: (CloneStatus.FRAME, 45, [CloneStatus.IMAGE_DONE, CloneStatus.FRAME_DONE]),
    6: (CloneStatus.SEGMENT_VIDEO, 60, [CloneStatus.IMAGE_DONE, CloneStatus.FRAME_DONE]),
    7: (CloneStatus.MERGE_VIDEO, 95, [CloneStatus.IMAGE_DONE, CloneStatus.FRAME_DONE, CloneStatus.SEGMENT_VIDEO_DONE]),
}


async def get_clone_script(db: AsyncSession, clone_script_id: int) -> CloneScript | None:
    result = await db.execute(select(CloneScript).where(CloneScript.id == clone_script_id))
    return result.scalar_one_or_none()


async def get_clone_script_by_script_id(db: AsyncSession, script_id: int) -> CloneScript | None:
    result = await db.execute(select(CloneScript).where(CloneScript.script_id == script_id))
    return result.scalar_one_or_none()


async def create_clone_script(
    db: AsyncSession,
    *,
    script_id: int,
    clone_theme: str,
    clone_requirements: dict | None = None,
) -> CloneScript:
    kwargs = {
        "script_id": script_id,
        "clone_theme": clone_theme,
        "clone_status": CloneStatus.PLOT.value,
        "clone_progress": 0,
    }
    if clone_requirements:
        kwargs["clone_requirements"] = clone_requirements
    clone_script = CloneScript(**kwargs)
    db.add(clone_script)
    await db.commit()
    await db.refresh(clone_script)
    return clone_script


async def reset_clone_plot(db: AsyncSession, clone_script_id: int) -> bool:
    """乐观锁重置复刻剧本状态。允许 PLOT_DONE（重跑）或 FAILED（失败重试）。"""
    result = await db.execute(
        update(CloneScript)
        .where(
            CloneScript.id == clone_script_id,
            CloneScript.clone_status.in_([CloneStatus.PLOT_DONE, CloneStatus.FAILED]),
        )
        .values({
            "clone_status": CloneStatus.PLOT,
            "clone_progress": 0,
            "clone_error_message": None,
            "clone_parse_pointer": None,
            "clone_parse_file_path": None,
        })
    )
    await db.commit()
    return result.rowcount > 0


async def advance_clone_step(
    db: AsyncSession,
    clone_script_id: int,
    step: int,
) -> CloneScript:
    """将复刻推进到指定阶段（乐观锁更新状态），返回 CloneScript。"""
    config = _CLONE_STEP_CONFIG.get(step)
    if config is None:
        raise HTTPException(status_code=400, detail=f"不支持的复刻阶段: {step}")

    new_status, new_progress, allowed_statuses = config

    result = await db.execute(
        update(CloneScript)
        .where(
            CloneScript.id == clone_script_id,
            CloneScript.clone_status.in_(allowed_statuses),
        )
        .values({
            "clone_status": new_status,
            "clone_progress": new_progress,
            "clone_error_message": None,
        })
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="任务已在运行或状态不正确")

    clone_script = await get_clone_script(db, clone_script_id)
    if not clone_script:
        raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")
    return clone_script


async def list_clone_scripts(
    db: AsyncSession,
    script_id: int,
    offset: int = 0,
    limit: int = 20,
) -> list[CloneScript]:
    result = await db.execute(
        select(CloneScript)
        .where(CloneScript.script_id == script_id)
        .order_by(CloneScript.updated_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all())


def clone_status_value(status) -> str:
    return status.value if status else CloneStatus.PENDING.value


async def get_clone_script_detail(db: AsyncSession, clone_script_id: int) -> dict:
    """一次性加载复刻详情（消除 N+1 查询），返回前端友好的 dict。"""
    clone_script = await get_clone_script(db, clone_script_id)
    if not clone_script:
        raise HTTPException(status_code=404, detail="复刻视频脚本不存在")

    plot_complete_status = list(CloneStatus)[2:-1]

    clone_script_content = ""
    voices = []
    segments = []
    images = []
    frames: list[CloneSegmentImg] = []
    segment_videos: list[CloneSegmentVideo] = []
    video: dict | None = None

    if clone_script.clone_status in plot_complete_status or (
        clone_script.clone_status == CloneStatus.FAILED
        and clone_script.clone_progress >= 20
    ):
        clone_parse_file_path = clone_script.clone_parse_file_path
        if clone_parse_file_path is None:
            raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
        clone_parse_file = Path(clone_parse_file_path)
        if not clone_parse_file.is_file():
            raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
        with open(clone_parse_file_path, "r", encoding="utf-8") as f:
            clone_script_content = f.read()

        # 一次性查询各资源（避免循环内逐条查询）
        result = await db.execute(
            select(CloneVoice)
            .where(CloneVoice.script_id == clone_script.id)
            .order_by(CloneVoice.sort_order)
        )
        voices = list(result.scalars().all())

        result = await db.execute(
            select(CloneScriptSegment)
            .options(
                selectinload(CloneScriptSegment.clone_segment_images),
                selectinload(CloneScriptSegment.clone_segment_video),
            )
            .where(CloneScriptSegment.script_id == clone_script.id)
            .order_by(CloneScriptSegment.start_time)
        )
        segments = list(result.scalars().all())

        result = await db.execute(
            select(CloneRoleImage)
            .where(CloneRoleImage.script_id == clone_script.id)
            .order_by(CloneRoleImage.created_at)
        )
        role_images = list(result.scalars().all())

        result = await db.execute(
            select(CloneSceneImage)
            .where(CloneSceneImage.script_id == clone_script.id)
            .order_by(CloneSceneImage.created_at)
        )
        scene_images = list(result.scalars().all())

        # 从已加载的关系中取子资源
        for segment in segments:
            if segment.clone_segment_images:
                frames.extend(segment.clone_segment_images)
            if segment.clone_segment_video:
                segment_videos.extend(segment.clone_segment_video)

        images = [
            {
                "id": img.id, "name": img.role_name, "width": img.width,
                "height": img.height, "desc": img.desc, "prompt": img.prompt,
                "seed": str(img.seed) if img.seed else None, "category": "role",
                "status": img.status.value, "version": img.version,
            }
            for img in role_images
        ]
        images += [
            {
                "id": img.id, "name": img.scene_name, "width": img.width,
                "height": img.height, "desc": img.desc, "prompt": img.prompt,
                "seed": str(img.seed) if img.seed else None, "category": "scene",
                "status": img.status.value, "version": img.version,
            }
            for img in scene_images
        ]

        result = await db.execute(
            select(CloneVideo).where(CloneVideo.video_id == clone_script.id)
        )
        video_data = result.scalar_one_or_none()
        if video_data:
            video = {
                "id": video_data.id,
                "category": "video",
                "duration": video_data.duration,
            }

    return {
        "id": clone_script_id,
        "content": clone_script_content,
        "voices": [
            {
                "id": voice.id, "role_name": voice.role_name,
                "duration": round(voice.duration, 2), "voice_type": voice.voice_type,
                "spk_id": voice.spk_id, "text": voice.text,
            }
            for voice in voices
        ],
        "segments": [
            {
                "id": seg.id, "start_time": seg.start_time, "end_time": seg.end_time,
                "shot_description": seg.shot_description,
                "dialogue": [
                    {
                        "speaker": lines["role_name"],
                        "text": "(" + lines["lines_flag"] + ")" + lines["lines"],
                    }
                    for lines in seg.dialogue
                ],
                "segment_type": seg.segment_type,
            }
            for seg in segments
        ],
        "images": [
            {
                "id": img["id"], "name": img["name"], "width": img["width"],
                "height": img["height"], "desc": img["desc"], "prompt": img["prompt"],
                "seed": img["seed"], "category": img["category"],
                "status": img["status"], "version": img["version"],
            }
            for img in images
        ],
        "frames": [
            {
                "id": frame.id, "name": f"分镜{i+1} 首帧",
                "width": frame.width, "height": frame.height,
                "desc": frame.desc, "prompt": frame.prompt, "seed": frame.seed,
                "category": "frame", "status": frame.status, "version": frame.version,
            }
            for i, frame in enumerate(frames)
        ],
        "segment_videos": [
            {
                "id": seg_v.id, "name": f"分镜{i+1} 视频",
                "width": seg_v.width, "height": seg_v.height,
                "desc": seg_v.desc, "prompt": seg_v.prompt, "seed": seg_v.seed,
                "category": "segment_video", "status": seg_v.status, "version": seg_v.version,
            }
            for i, seg_v in enumerate(segment_videos)
        ],
        "video": video,
    }


async def get_voice(db: AsyncSession, voice_id: str) -> CloneVoice | None:
    result = await db.execute(select(CloneVoice).where(CloneVoice.id == voice_id))
    return result.scalar_one_or_none()


async def get_image_by_category(
    db: AsyncSession,
    category: Literal["role", "scene", "frame"],
    image_id: int,
):
    model_map = {
        "role": CloneRoleImage,
        "scene": CloneSceneImage,
        "frame": CloneSegmentImg,
    }
    model = model_map.get(category)
    if model is None:
        raise HTTPException(status_code=404, detail="check category in [role, scene, frame]")
    result = await db.execute(select(model).where(model.id == image_id))
    return result.scalar_one_or_none()


async def get_video_by_category(
    db: AsyncSession,
    category: Literal["segment_video", "merged"],
    video_id: int,
):
    if category == "segment_video":
        result = await db.execute(select(CloneSegmentVideo).where(CloneSegmentVideo.id == video_id))
        obj = result.scalar_one_or_none()
        return obj, (obj.path if obj else None)
    elif category == "merged":
        result = await db.execute(select(CloneVideo).where(CloneVideo.id == video_id))
        obj = result.scalar_one_or_none()
        return obj, (obj.file_path if obj else None)
    raise HTTPException(status_code=404, detail="check category in [segment_video, merged]")

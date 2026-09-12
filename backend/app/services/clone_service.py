"""复刻业务逻辑层：负责 CloneScript 各阶段的状态流转与详情组装，与路由层解耦。

阶段 step 映射（与 LangGraph clone.py 的 step 对应）：
    1 = plot（剧本）   2 = segments（分镜）   3 = voice（配音）
    4 = images（生图）  5 = frames（参考帧） 6 = segment_videos（分镜视频）
    7 = video（合并成片）
"""
from pathlib import Path
from typing import Literal
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, or_, select, update
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
    GenerateFlowStatus,
    Script,
)
from app.models.video import Video
from app.models.user import User
from app.util import FRAME_BEGIN_PROGRESS, IMAGE_BEGIN_PROGRESS, MERGE_VIDEO_BEGIN_PROGRESS, SEGMENT_BEGIN_PROGRESS, SEGMENT_VIDEO_BEGIN_PROGRESS, VOICE_BEGIN_PROGRESS, get_md5, logger

# 北京时间 UTC+8
BJ_TZ = timezone(timedelta(hours=8))

# 分镜时间轴校准常量
SEGMENT_AUDIO_TAIL_PAD = 0.3   # 镜尾留白（秒），避免台词贴边
SEGMENT_MIN_DURATION = 1.0     # 单镜最短时长（秒），与分镜 LLM 约束 ge=1.0 对齐
SEGMENT_MAX_DURATION = 15.0    # 单镜最长时长（秒），与 GROUP_MAX_DURATION 对齐
SEGMENT_CONTINUATION_PAD = 0.5 # 跨镜台词延续段(body/tail)的衔接留白（秒），不计入整句音频


# 渲染进行中的状态：处于这些状态时不允许再次触发渲染，避免整条流水线被覆盖重跑
IN_PROGRESS_FLOW_STATUSES = [
    GenerateFlowStatus.VOICE,
    GenerateFlowStatus.IMAGE,
    GenerateFlowStatus.FRAME,
    GenerateFlowStatus.SEGMENT_VIDEO,
    GenerateFlowStatus.MERGE_VIDEO,
]

# step -> (进入状态, 进度, 前置允许状态列表)
# 复刻剧本 = plot(1) + segments(2)；渲染 = voice(3) + images(4) + video(6) + merge(7)
_CLONE_STEP_CONFIG = {
    2: (CloneStatus.SEGMENTS, SEGMENT_BEGIN_PROGRESS, [CloneStatus.PLOT_DONE, CloneStatus.SEGMENTS_DONE]),
    3: (GenerateFlowStatus.VOICE, VOICE_BEGIN_PROGRESS, [CloneStatus.SEGMENTS_DONE, GenerateFlowStatus.VOICE_DONE, GenerateFlowStatus.FAILED]),
    4: (GenerateFlowStatus.IMAGE, IMAGE_BEGIN_PROGRESS, [CloneStatus.SEGMENTS_DONE, GenerateFlowStatus.VOICE_DONE, GenerateFlowStatus.IMAGE_DONE, GenerateFlowStatus.FAILED]),
    5: (GenerateFlowStatus.FRAME, FRAME_BEGIN_PROGRESS, [GenerateFlowStatus.IMAGE_DONE, GenerateFlowStatus.FRAME_DONE, GenerateFlowStatus.FAILED]),
    6: (GenerateFlowStatus.SEGMENT_VIDEO, SEGMENT_VIDEO_BEGIN_PROGRESS, [GenerateFlowStatus.IMAGE_DONE, GenerateFlowStatus.FRAME_DONE, GenerateFlowStatus.SEGMENT_VIDEO_DONE, GenerateFlowStatus.SEGMENT_VIDEO, GenerateFlowStatus.FAILED]),
    7: (GenerateFlowStatus.MERGE_VIDEO, MERGE_VIDEO_BEGIN_PROGRESS, [GenerateFlowStatus.SEGMENT_VIDEO_DONE, GenerateFlowStatus.SEGMENT_VIDEO, GenerateFlowStatus.MERGE_VIDEO_DONE, GenerateFlowStatus.FAILED]),
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
    source_type: str = "CLONE",
) -> CloneScript:
    kwargs = {
        "script_id": script_id,
        "clone_theme": clone_theme,
        "source_type": source_type,
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


async def create_original_render(db: AsyncSession, video_id: int) -> CloneScript:
    """从原片解析结果创建 ORIGINAL 渲染工作台（原片直转渲染）。

    仅创建工作台记录（source_type=ORIGINAL，中性主题"原片直转"）；
    后续由 clone_video_task 跑 plot+storyboard 生成 clone_parse_pointer 与
    clone_script_segments，再进入 voice/image/video/merge 渲染。
    """
    result = await db.execute(select(Script).where(Script.video_id == video_id))
    script = result.scalar_one_or_none()
    if not script:
        raise HTTPException(status_code=404, detail="原视频脚本不存在，请先完成视频解析")
    return await create_clone_script(
        db,
        script_id=script.id,
        clone_theme="原片直转",
        source_type="ORIGINAL",
    )


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
            "clone_parse_script": None,
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

    logger.info(f'new_status:{new_status}, new_progress:{new_progress}, allowed_statuses:{allowed_statuses}')

    # 按枚举类型拆分 allowed_statuses，避免跨枚举值传入错误的 PostgreSQL enum 列
    clone_allowed = [s for s in allowed_statuses if isinstance(s, CloneStatus)]
    generate_allowed = [s for s in allowed_statuses if isinstance(s, GenerateFlowStatus)]

    if step == 2:
        result = await db.execute(
            update(CloneScript)
            .where(
                CloneScript.id == clone_script_id,
                CloneScript.clone_status.in_(clone_allowed),
            )
            .values({
                "clone_status": new_status,
                "clone_progress": new_progress,
                "clone_error_message": None,
            })
        )
    else:
        # 动态构建 OR 条件：只包含有合法值的枚举列
        or_conditions = []
        if generate_allowed:
            or_conditions.append(CloneScript.generate_flow_status.in_(generate_allowed))
        if clone_allowed:
            # clone_status 兜底（如复刻剧本 SEGMENTS_DONE 起跑渲染）仅在当前没有渲染进行中时生效，
            # 否则渲染进行中重复触发会整条流水线覆盖重跑。
            or_conditions.append(and_(
                CloneScript.clone_status.in_(clone_allowed),
                or_(
                    CloneScript.generate_flow_status.is_(None),
                    CloneScript.generate_flow_status.notin_(IN_PROGRESS_FLOW_STATUSES),
                ),
            ))

        if not or_conditions:
            raise HTTPException(status_code=400, detail="无可匹配的状态条件")

        result = await db.execute(
            update(CloneScript)
            .where(CloneScript.id == clone_script_id, or_(*or_conditions))
            .values({
                "generate_flow_status": new_status,
                "generate_flow_progress": new_progress,
                "clone_error_message": None,
            })
        )
    await db.commit()
    if result.rowcount == 0:
        # 区分「渲染进行中」与「状态不匹配」，前者给出更明确的提示
        current = await get_clone_script(db, clone_script_id)
        if current and current.generate_flow_status in IN_PROGRESS_FLOW_STATUSES:
            raise HTTPException(status_code=409, detail="任务正在进行中，请等待完成后再操作")
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


def generate_flow_status_value(status) -> str:
    return status.value if status else GenerateFlowStatus.PENDING.value


async def list_all_clone_scripts(
    db: AsyncSession,
    user: User,
    offset: int = 0,
    limit: int = 50,
) -> list[dict]:
    """列出当前用户可见的复刻剧本（超管可见全部），附带原视频信息（含小说来源）。

    归属取最外层：视频来源看 Video.user_id，小说来源看 Novel.user_id。
    """
    from app.models.novel import Novel

    stmt = (
        select(CloneScript, Script, Video, Novel.title.label("novel_title"))
        .outerjoin(Script, CloneScript.script_id == Script.id)
        .outerjoin(Video, Script.video_id == Video.id)
        .outerjoin(Novel, CloneScript.novel_id == Novel.id)
    )
    if not user.is_superuser:
        stmt = stmt.where(or_(Video.user_id == user.id, Novel.user_id == user.id))

    result = await db.execute(
        stmt.order_by(CloneScript.created_at.desc()).offset(offset).limit(limit)
    )
    rows = result.all()
    return [
        {
            "id": cs.id,
            "script_id": cs.script_id,
            "video_id": v.id if v else None,
            "video_title": v.title if v else (novel_title or "未命名小说"),
            "video_category": v.category if v else None,
            "clone_theme": cs.clone_theme,
            "clone_status": clone_status_value(cs.clone_status),
            "clone_progress": cs.clone_progress or 0,
            "generate_flow_status": generate_flow_status_value(cs.generate_flow_status),
            "generate_flow_progress": cs.generate_flow_progress or 0,
            "error_message": cs.clone_error_message,
            "source_type": cs.source_type,
            "created_at": cs.created_at.isoformat() if cs.created_at else None,
        }
        for cs, s, v, novel_title in rows
    ]


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
        clone_script_content = ''
        logger.info(f'clone_parse_file_path:{clone_script.clone_parse_file_path}')
        # clone_parse_file_path = clone_script.clone_parse_file_path
        # if clone_parse_file_path is None:
        #     raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
        # clone_parse_file = Path(clone_parse_file_path)
        # if not clone_parse_file.is_file():
        #     raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
        # with open(clone_parse_file_path, "r", encoding="utf-8") as f:
        #     clone_script_content = f.read()

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
        "source_type": clone_script.source_type,
        "clone_status": clone_status_value(clone_script.clone_status),
        "clone_progress": clone_script.clone_progress or 0,
        "generate_flow_status": generate_flow_status_value(clone_script.generate_flow_status),
        "generate_flow_progress": clone_script.generate_flow_progress or 0,
        "error_message": clone_script.clone_error_message,
        "content": clone_script_content,
        "clone_parse_pointer": clone_script.clone_parse_pointer,
        "clone_parse_script": clone_script.clone_parse_script,
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
        "created_at": clone_script.created_at.replace(tzinfo=timezone.utc).astimezone(BJ_TZ).isoformat() if clone_script.created_at else None,
    }


async def get_voice(db: AsyncSession, voice_id: int) -> CloneVoice | None:
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


async def sync_segment_timeline(clone_script_id: int, db: AsyncSession | None = None) -> int:
    """配音完成后，用真实音频时长校准分镜时间轴（音画对齐）。

    分镜落库时的 start_time/end_time 取自 LLM 预估的 duration_budget；
    配音阶段生成的 CloneVoice 才是音轨的真实内容。这里把每个分镜时长重算为
    "镜内真实音频总长 + 镜尾留白"，并重新累加 offset，保证后续生图 / 分镜视频 /
    合并拿到的分镜时长与真实音轨一致——避免台词被截断或尾部空镜。

    规则：
    - 含有真实配音的分镜：时长 = 镜内真实音频总长 + 镜尾留白，并钳制在 [1, 15]s。
    - 跨镜长台词（lines_flag 为 body/tail 的延续段）不重复计入整句音频，
      只给衔接留白；整句音频只在该镜的 head/all 段计入一次，避免成片台词重读。
    - 无配音可锚定的分镜：保持原有时长，仅随上游重排。
    - 幂等：可安全地在配音完成后、推进生图前重复调用（重算结果不变）。

    Returns:
        时长发生变更的分镜数量（0 表示无需校准）。
    """
    owns_db = db is None
    if owns_db:
        # 延迟导入 process_loop：避免 app.tasks.__init__ -> parse_video -> clone -> clone_voice -> clone_service 的循环导入
        from app.tasks.process_loop_manager import process_loop
        db = process_loop.AsyncSessionLocal()
    try:
        # 1. 加载该脚本真实配音时长，(role_name, voice_type, text_md5) 精准匹配
        result = await db.execute(
            select(CloneVoice).where(CloneVoice.script_id == clone_script_id)
        )
        voices = result.scalars().all()
        if not voices:
            logger.info(f'sync_segment_timeline: script_id={clone_script_id} 无配音记录，跳过校准')
            return 0

        voice_duration = {}
        for voice in voices:
            voice_duration[(voice.role_name, voice.voice_type, voice.text_md5)] = voice.duration

        # 2. 按时间顺序加载分镜
        result = await db.execute(
            select(CloneScriptSegment)
            .where(CloneScriptSegment.script_id == clone_script_id)
            .order_by(CloneScriptSegment.start_time)
        )
        segments = list(result.scalars().all())
        if not segments:
            return 0

        # 3. 逐镜重算时长，并重新累加时间轴（无音频的分镜沿用原时长参与排布）
        offset = 0.0
        changed = 0
        for seg in segments:
            audio_sum = 0.0
            matched = False
            for line in (seg.dialogue or []):
                search_md5 = get_md5(line.get('lines') or '')
                dur = voice_duration.get(
                    (line.get('role_name'), line.get('audio_style'), search_md5)
                )
                if dur is None:
                    # 该行无配音：沿用分镜里给它占的时间槽（静音）
                    audio_sum += max(0.0, (line.get('end_offset') or 0) - (line.get('start_offset') or 0))
                    continue
                matched = True
                if line.get('lines_flag') in ('body', 'tail'):
                    # 跨镜台词的延续段：整句音频只在 head/all 计入一次，这里仅留衔接
                    audio_sum += SEGMENT_CONTINUATION_PAD
                else:
                    # all / head / 未知：在该镜完整计入真实音频
                    audio_sum += dur

            if matched:
                new_dur = min(SEGMENT_MAX_DURATION, max(SEGMENT_MIN_DURATION, audio_sum + SEGMENT_AUDIO_TAIL_PAD))
            else:
                new_dur = seg.end_time - seg.start_time
                if new_dur <= 0:
                    new_dur = SEGMENT_MIN_DURATION

            old_start, old_end = seg.start_time, seg.end_time
            seg.start_time = round(offset, 2)
            seg.end_time = round(offset + new_dur, 2)
            offset += new_dur
            if abs(old_start - seg.start_time) > 0.001 or abs(old_end - seg.end_time) > 0.001:
                changed += 1

        await db.commit()
        logger.info(
            f'sync_segment_timeline: script_id={clone_script_id} 校准 {len(segments)} 个分镜, '
            f'改动 {changed} 个, 校准后总时长 {round(offset, 2)}s'
        )
        return changed
    except Exception:
        await db.rollback()
        logger.exception(f'sync_segment_timeline 校准分镜时间轴失败: clone_script_id={clone_script_id}')
        raise
    finally:
        if owns_db:
            await db.close()

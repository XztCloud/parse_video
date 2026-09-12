"""小说转剧本编排服务

调用novel_parser解析小说，调用novel_analysis分析片段，保存到数据库。
"""

from __future__ import annotations

import json
from pathlib import Path

from celery.utils.log import get_task_logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.novel import Novel
from app.models.script import CloneScript, CloneScriptSegment, CloneStatus
from app.services.llm import CloneAnalysisFocus, CloneAnalysisPlot
from app.services.novel_parser import SceneChunk, parse_novel
from app.services.novel_analysis import analyze_novel_full
from app.util import make_dir
from sqlalchemy import delete, select
from app.tasks.process_loop_manager import process_loop

logger = get_task_logger(__name__)


async def generate_novel_scripts(
    novel_id: int,
    theme: str,
    requirements: dict | None = None,
    auto_run: bool = False
) -> list[int]:
    """完整pipeline：解析小说 → 分析片段 → 创建CloneScripts

    Args:
        novel_id: 小说ID
        theme: 主题（用于CloneScript.clone_theme）
        requirements: 额外要求（用于CloneScript.clone_requirements）
        auto_run: 是否自动运行下游pipeline

    Returns:
        创建的CloneScript ID列表
    """

    async with process_loop.AsyncSessionLocal() as db:
        return await _generate_novel_scripts_inner(novel_id, theme, requirements, auto_run, db)



async def _generate_novel_scripts_inner(
    novel_id: int,
    theme: str,
    requirements: dict | None,
    auto_run: bool,
    db: AsyncSession,
) -> list[int]:
    """内部实现：完整pipeline"""
    from sqlalchemy import select, update
    from sqlalchemy.orm import Session

    # 1. 获取小说信息
    result = await db.execute(
        select(Novel).where(Novel.id == novel_id)
    )
    novel = result.scalar_one_or_none()
    if not novel:
        raise ValueError(f"Novel with id {novel_id} not found")

    try:
        # 删除旧数据
        await db.execute(
            delete(CloneScript).where(CloneScript.novel_id == novel_id)
        )
        await db.execute(
            delete(CloneScriptSegment).where(CloneScript.novel_id == novel_id)
        )
        await db.commit()
        
        # 2. 解析小说（每章节产出一个SceneChunk，不在此处做角色/场景识别）
        logger.info(f"Parsing novel: {novel.title}")
        full_text, chapters, scene_chunks = parse_novel(novel.file_path)

        logger.info(f'get scene_chunks: {scene_chunks}')

        # 更新章节数量
        await db.execute(
            update(Novel)
            .where(Novel.id == novel_id)
            .values(chapter_count=len(chapters))
        )
        await db.commit()

        total_chunks = len(scene_chunks)
        logger.info(f"Novel parsed: {len(chapters)} chapters, {total_chunks} scene chunks")

        # 3. 分析所有片段
        logger.info(f"Analyzing {total_chunks} scene chunks")
        analysis_results = await analyze_novel_full(scene_chunks)

        # 4. 保存到数据库
        clone_script_ids: list[int] = []
        for i, (chunk, (focus, plot)) in enumerate(zip(scene_chunks, analysis_results)):
            logger.info(f"Saving chunk {i + 1}/{total_chunks}")

            # 创建CloneScript
            clone_script = await _save_analysis_to_clone_script(
                db=db,
                novel_id=novel_id,
                chunk=chunk,
                focus=focus,
                plot=plot,
                theme=theme,
                requirements=requirements,
                chunk_index=i,
                total_chunks=total_chunks,
            )
            clone_script_ids.append(clone_script.id)

            # 更新进度
            progress = int((i + 1) / total_chunks * 100)
            await db.execute(
                update(Novel)
                .where(Novel.id == novel_id)
                .values(progress=progress)
            )
            await db.commit()
        
        # 更新状态为完成
        await db.execute(
            update(Novel)
            .where(Novel.id == novel_id)
            .values(status="DONE", progress=100)
        )
        await db.commit()

        logger.info(f"Successfully created {len(clone_script_ids)} CloneScripts")

        # 5. 可选：自动运行下游pipeline
        if auto_run:
            logger.info("Auto-running downstream pipeline for all CloneScripts")

        return clone_script_ids

    except Exception as e:
        # 更新状态为失败
        await db.execute(
            update(Novel)
            .where(Novel.id == novel_id)
            .values(status="FAILED", error_message=str(e)[:500])
        )
        await db.commit()
        raise


async def _save_analysis_to_clone_script(
    db: AsyncSession,
    novel_id: int,
    chunk: SceneChunk,
    focus: CloneAnalysisFocus,
    plot: CloneAnalysisPlot,
    theme: str,
    requirements: dict | None,
    chunk_index: int,
    total_chunks: int,
) -> CloneScript:
    """保存分析结果到CloneScript

    Args:
        db: 数据库会话
        novel_id: 小说ID
        chunk: 章节块
        focus: CloneAnalysisFocus分析结果
        plot: CloneAnalysisPlot分析结果
        theme: 主题
        requirements: 额外要求
        chunk_index: 当前片段索引
        total_chunks: 总片段数

    Returns:
        创建的CloneScript
    """
    # 构建clone_requirements，包含元数据
    clone_requirements = requirements or {}
    clone_requirements.update({
        "chapter_index": chunk.chapter_index,
        "chapter_title": chunk.chapter_title,
        "scene_index": chunk.scene_index,
        "total_scenes": total_chunks,
        "source_type": "NOVEL",
    })

    # 创建CloneScript
    clone_script = CloneScript(
        script_id=None,  # 小说来源没有script_id
        novel_id=novel_id,
        source_type="NOVEL",
        clone_theme=theme,
        clone_requirements=clone_requirements,
        clone_parse_pointer=focus.model_dump(),
        clone_parse_script=plot.model_dump(),
        clone_status=CloneStatus.PLOT_DONE,  # 直接跳到PLOT_DONE状态
        clone_progress=100,
    )
    db.add(clone_script)
    
    await db.commit()
    await db.refresh(clone_script)

    logger.info(f"Created CloneScript {clone_script.id} for chunk {chunk_index}")

    # 生成该CloneScript的分镜列表（CloneScriptSegment）
    await _save_plot_to_clone_segments(db, clone_script, plot)

    # 生成markdown文件（可选）
    await _generate_markdown_file(clone_script, chunk, focus, plot, db)

    return clone_script


async def _save_plot_to_clone_segments(
    db: AsyncSession,
    clone_script: CloneScript,
    plot: CloneAnalysisPlot,
) -> int:
    """把剧情段落（plot_script）落库为CloneScriptSegment分镜列表

    直接复用复刻CLONE流程的整条分镜状态机 clone_storyboard_graph：
    LLM 根据角色库/场景库/剧情段落产出每个分镜的 role_view_info 出场信息
    （含不说话但出镜的角色），再落库为CloneScriptSegment，
    供下游角色/首帧图片、分镜视频等流程复用。

    Args:
        db: 数据库会话
        clone_script: 已创建的CloneScript
        plot: 剧情分析结果（仅用于确认plot已写入clone_parse_script）

    Returns:
        创建的分镜数量
    """
    from app.services.clone_storyboard import clone_storyboard_graph

    # 小说来源在voice阶段之前先生成分镜，没有CloneVoice，require_voice=False跳过音频强校验
    state = {
        "clone_script_id": clone_script.id,
        "storyboard_script": None,
        "plot_role_library": {},
        "plot_scene_library": {},
        "character_manifest": None,
        "role_asset_library": {},
        "scene_asset_library": {},
        "error": "",
        "retry_cnt": 0,
        "retry_messages": '',
        "require_voice": False,
    }
    await clone_storyboard_graph.ainvoke(state)

    # 统计落库的分镜数
    from sqlalchemy import func, select
    from app.models.script import CloneScriptSegment
    count = (await db.execute(
        select(func.count())
        .select_from(CloneScriptSegment)
        .where(CloneScriptSegment.script_id == clone_script.id)
    )).scalar() or 0
    logger.info(f"Created {count} CloneScriptSegments for CloneScript {clone_script.id}")
    return count


async def _generate_markdown_file(
    clone_script: CloneScript,
    chunk: SceneChunk,
    focus: CloneAnalysisFocus,
    plot: CloneAnalysisPlot,
    db: AsyncSession
) -> None:
    """生成markdown格式的剧本文件"""
    try:
        # 构建输出目录
        output_dir = Path(settings.UPLOAD_DIR) / "novels" / str(clone_script.novel_id)
        make_dir(str(output_dir))

        # 构建文件名
        filename = f"script_{clone_script.id}_ch{chunk.chapter_index}_s{chunk.scene_index}.md"
        filepath = output_dir / filename

        # 生成markdown内容
        md_content = f"""# {clone_script.clone_theme}

## 片段信息
- **章节**: {chunk.chapter_title}
- **场景**: {chunk.scene_index + 1}
- **时长**: {chunk.estimated_duration_seconds:.1f}秒
- **字符数**: {chunk.char_count}

## 角色列表
"""
        for role in focus.role_library:
            md_content += f"- **{role.role_name}**: {role.effect}\n"

        md_content += "\n## 场景列表\n"
        for scene in focus.scene_library:
            md_content += f"- **{scene.scene_name}**: {scene.environment_description}\n"

        md_content += "\n## 剧情大纲\n"
        for script in plot.plot_script:
            md_content += f"\n### {script.paragraph_theme}\n"
            md_content += f"**时间**: {script.start_time:.1f}s - {script.end_time:.1f}s\n\n"
            md_content += f"**画面描述**: {script.screen_description}\n\n"
            if script.actor_lines:
                md_content += "**台词**:\n"
                for line in script.actor_lines:
                    md_content += f"- {line.role_name}: {line.lines} ({line.predict_duration:.1f}s)\n"

        # 写入文件
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(md_content)

        # 更新clone_parse_file_path
        clone_script.clone_parse_file_path = str(filepath)
        await db.commit()

        logger.info(f"Generated markdown file: {filepath}")

    except Exception as e:
        logger.warning(f"Failed to generate markdown file: {e}")


async def get_novel_scripts(
    db: AsyncSession,
    novel_id: int,
) -> list[CloneScript]:
    """获取小说的所有CloneScript

    Args:
        db: 数据库会话
        novel_id: 小说ID

    Returns:
        CloneScript列表
    """
    from sqlalchemy import select

    result = await db.execute(
        select(CloneScript)
        .where(CloneScript.novel_id == novel_id)
        .order_by(CloneScript.id)
    )
    return list(result.scalars().all())

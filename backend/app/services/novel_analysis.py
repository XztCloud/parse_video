"""小说片段LLM分析服务

将小说片段转换为CloneAnalysisFocus + CloneAnalysisPlot结构。
参考ai-novel2script的质量门禁，添加场景目标、冲突、转折点等戏剧元素。
"""

from __future__ import annotations

import json
from typing import Any

from celery.utils.log import get_task_logger
from langchain_core.messages import HumanMessage, SystemMessage

from app.services.llm import (
    CloneAnalysisFocus,
    CloneAnalysisPlot,
    ClonePlotScript,
    CharacterInfo,
    SceneDetail,
    SceneStyleGlobal,
    ActorLines,
    ainvoke_structured_robust,
    model,
)
from app.services.novel_parser import SceneChunk

logger = get_task_logger(__name__)

# System Prompt for Novel Analysis
NOVEL_ANALYSIS_SYSTEM_PROMPT = """# Role

你是一位资深的影视编剧和短视频导演。你擅长将文学小说改编为短视频剧本，保留原作的核心氛围、情节张力和人物关系。

# Task

阅读用户提供的【小说片段】，将其改编为一段短视频剧情大纲。

# Rules

1. 忠于原作：保留原文的核心情节、人物关系和氛围基调
2. 视觉化改编：将文学描写转化为可拍摄的画面描述
3. 台词设计：为角色设计符合原作性格的台词（旁白用于叙述性文字）
4. 每段剧情的台词预估时长之和 <= 该段剧情时长（中文约4.5字/秒）
5. 场景描述必须具体、视觉化，避免抽象描述
6. 角色名必须一致：同一个角色在所有片段中使用相同的名字
7. 场景名必须一致：同一个场景在所有片段中使用相同的名称和描述

# Output Structure

你必须输出以下结构：

## role_library（角色列表）
复用已有角色，新增角色补充进来。每个角色包含：
- role_name: 角色名（必须与已有角色名一致）
- gender: 性别（male/female）
- age: 年龄（数字）
- voice_style_guide: 声音风格描述（如有台词）
- effect: 角色在剧本中的作用

## scene_library（场景列表）
复用已有场景，新增场景补充进来。每个场景包含：
- scene_name: 场景名（必须与已有场景名一致）
- environment_description: 环境描述（具体、可视化）
- color_grading: 调色风格

## global_style（全局画风）
保持与前段一致或更新：
- global_style_suffix: 全局生图后缀（中文提示词）

## plot_script（剧情段落列表）
每段包含：
- start_time: 开始时间（秒）
- end_time: 结束时间（秒）
- paragraph_theme: 本段主题（10字以内）
- screen_description: 画面描述（具体、可视化）
- actor_lines: 台词列表（角色名+台词内容+预估时长）

# Quality Checks

确保输出满足：
1. 所有角色都已识别并命名
2. 场景地点明确（INT/EXT + 具体地点）
3. 时间明确（DAY/NIGHT/DUSK/DAWN）
4. 每个段落都有明确的戏剧目标
5. 冲突和转折点清晰
6. 台词总时长不超过片段时长限制
"""


def build_novel_analysis_focus_prompt(
    chunk: SceneChunk,
    existing_roles: list[CharacterInfo],
    existing_scenes: list[SceneDetail],
    global_style: SceneStyleGlobal | None,
    total_chunks: int,
) -> list[SystemMessage | HumanMessage]:
    """构建小说分析Focus的prompt（角色库、场景库、全局画风）"""
    roles_info = "无" if not existing_roles else json.dumps(
        [r.model_dump() for r in existing_roles],
        ensure_ascii=False,
        indent=2
    )

    scenes_info = "无" if not existing_scenes else json.dumps(
        [s.model_dump() for s in existing_scenes],
        ensure_ascii=False,
        indent=2
    )

    style_info = "无" if not global_style else json.dumps(
        global_style.model_dump(),
        ensure_ascii=False,
        indent=2
    )

    query_prompt = f"""请分析以下小说片段，提取角色、场景和画风信息。

1. 【小说片段】
```Text
{chunk.text}
```

2. 【已有角色库】（前续片段已建立的角色）
```Json
{roles_info}
```

3. 【已有场景库】（前续片段已建立的场景）
```Json
{scenes_info}
```

4. 【全局画风】（如有）
```Json
{style_info}
```

5. 【片段元信息】
- 章节：{chunk.chapter_title}
- 位置：第{chunk.scene_index + 1}/{total_chunks}段
- 本段文字约{chunk.char_count}字

请提取：
- role_library: 角色列表（复用已有角色，新增角色补充进来）
- scene_library: 场景列表（复用已有场景，新增场景补充进来）
- global_style: 全局画风（保持与前段一致或更新）

请严格按照CloneAnalysisFocus结构输出JSON格式。
"""

    return [
        SystemMessage(content=NOVEL_ANALYSIS_SYSTEM_PROMPT),
        HumanMessage(content=query_prompt),
    ]


def build_novel_analysis_plot_prompt(
    chunk: SceneChunk,
    focus: CloneAnalysisFocus,
    total_chunks: int,
) -> list[SystemMessage | HumanMessage]:
    """构建小说分析Plot的prompt（剧情段落）"""
    # 构建角色库信息
    roles_info = json.dumps(
        [r.model_dump() for r in focus.role_library],
        ensure_ascii=False,
        indent=2
    )

    # 构建场景库信息
    scenes_info = json.dumps(
        [s.model_dump() for s in focus.scene_library],
        ensure_ascii=False,
        indent=2
    )

    query_prompt = f"""请分析以下小说片段，生成剧情段落。

1. 【小说片段】
```Text
{chunk.text}
```

2. 【角色库】
```Json
{roles_info}
```

3. 【场景库】
```Json
{scenes_info}
```

4. 【片段元信息】
- 章节：{chunk.chapter_title}
- 位置：第{chunk.scene_index + 1}/{total_chunks}段
- 本段文字约{chunk.char_count}字
- 预估时长：{chunk.estimated_duration_seconds:.1f}秒

请生成plot_script，每段包含：
- start_time: 开始时间（秒）
- end_time: 结束时间（秒）
- paragraph_theme: 本段主题（10字以内）
- screen_description: 画面描述（具体、可视化）
- actor_lines: 台词列表（角色名+台词内容+预估时长）

请严格按照CloneAnalysisPlot结构输出JSON格式。
"""

    return [
        SystemMessage(content=NOVEL_ANALYSIS_SYSTEM_PROMPT),
        HumanMessage(content=query_prompt),
    ]


async def analyze_novel_chunk(
    chunk: SceneChunk,
    existing_roles: list[CharacterInfo],
    existing_scenes: list[SceneDetail],
    global_style: SceneStyleGlobal | None,
    total_chunks: int,
    retry_count: int = 3,
) -> tuple[CloneAnalysisFocus, CloneAnalysisPlot]:
    """分析单个小说片段

    分两次调用LLM，分别输出CloneAnalysisFocus和CloneAnalysisPlot，
    避免达到LLM最大长度限制。

    Args:
        chunk: 场景块
        existing_roles: 已有角色列表
        existing_scenes: 已有场景列表
        global_style: 全局画风
        total_chunks: 总场景块数
        retry_count: 重试次数

    Returns:
        (CloneAnalysisFocus, CloneAnalysisPlot)

    Raises:
        Exception: 如果分析失败
    """
    # 第一次调用：生成CloneAnalysisFocus（角色库、场景库、全局画风）
    focus = await _generate_clone_analysis_focus(
        chunk, existing_roles, existing_scenes, global_style, total_chunks, retry_count
    )

    # 第二次调用：生成CloneAnalysisPlot（剧情段落）
    plot = await _generate_clone_analysis_plot(
        chunk, focus, total_chunks, retry_count
    )

    # 验证台词时长
    _validate_line_durations(plot, chunk.estimated_duration_seconds)

    return focus, plot


async def _generate_clone_analysis_focus(
    chunk: SceneChunk,
    existing_roles: list[CharacterInfo],
    existing_scenes: list[SceneDetail],
    global_style: SceneStyleGlobal | None,
    total_chunks: int,
    retry_count: int,
) -> CloneAnalysisFocus:
    """生成CloneAnalysisFocus（角色库、场景库、全局画风）"""
    messages = build_novel_analysis_focus_prompt(
        chunk, existing_roles, existing_scenes, global_style, total_chunks
    )

    structured_model = model.with_structured_output(CloneAnalysisFocus)

    for attempt in range(retry_count):
        try:
            logger.info(f"Generating focus for chunk {chunk.chapter_index}-{chunk.scene_index}, attempt {attempt + 1}")
            focus = await ainvoke_structured_robust(
                structured_model,
                CloneAnalysisFocus,
                messages,
                name=f"novel_analysis_focus_{chunk.chapter_index}_{chunk.scene_index}",
            )
            return focus
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == retry_count - 1:
                raise

    raise Exception(f"Failed to generate focus after {retry_count} attempts")


async def _generate_clone_analysis_plot(
    chunk: SceneChunk,
    focus: CloneAnalysisFocus,
    total_chunks: int,
    retry_count: int,
) -> CloneAnalysisPlot:
    """生成CloneAnalysisPlot（剧情段落）"""
    messages = build_novel_analysis_plot_prompt(chunk, focus, total_chunks)

    structured_model = model.with_structured_output(CloneAnalysisPlot)

    for attempt in range(retry_count):
        try:
            logger.info(f"Generating plot for chunk {chunk.chapter_index}-{chunk.scene_index}, attempt {attempt + 1}")
            plot = await ainvoke_structured_robust(
                structured_model,
                CloneAnalysisPlot,
                messages,
                name=f"novel_analysis_plot_{chunk.chapter_index}_{chunk.scene_index}",
            )
            return plot
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt == retry_count - 1:
                raise

    raise Exception(f"Failed to generate plot after {retry_count} attempts")


def _validate_line_durations(plot: CloneAnalysisPlot, max_duration: float) -> None:
    """验证台词总时长是否超过限制"""
    total_duration = sum(
        line.predict_duration
        for script in plot.plot_script
        for line in script.actor_lines
    )
    if total_duration > max_duration:
        logger.warning(
            f"Total line duration {total_duration:.1f}s exceeds chunk duration {max_duration:.1f}s"
        )


async def analyze_novel_full(
    scene_chunks: list[SceneChunk],
) -> list[tuple[CloneAnalysisFocus, CloneAnalysisPlot]]:
    """分析所有小说片段，保持上下文连贯性

    Args:
        scene_chunks: 场景块列表

    Returns:
        分析结果列表，每个元素为(CloneAnalysisFocus, CloneAnalysisPlot)
    """
    all_results: list[tuple[CloneAnalysisFocus, CloneAnalysisPlot]] = []
    accumulated_roles: list[CharacterInfo] = []
    accumulated_scenes: list[SceneDetail] = []
    global_style: SceneStyleGlobal | None = None

    total_chunks = len(scene_chunks)

    for i, chunk in enumerate(scene_chunks):
        logger.info(f"Processing chunk {i + 1}/{total_chunks}: {chunk.chapter_title} - Scene {chunk.scene_index}")

        # 分析当前片段
        focus, plot = await analyze_novel_chunk(
            chunk,
            accumulated_roles,
            accumulated_scenes,
            global_style,
            total_chunks,
        )

        # 累积角色（去重）
        existing_role_names = {r.role_name for r in accumulated_roles}
        for role in focus.role_library:
            if role.role_name not in existing_role_names:
                accumulated_roles.append(role)
                existing_role_names.add(role.role_name)

        # 累积场景（去重）
        existing_scene_names = {s.scene_name for s in accumulated_scenes}
        for scene in focus.scene_library:
            if scene.scene_name not in existing_scene_names:
                accumulated_scenes.append(scene)
                existing_scene_names.add(scene.scene_name)

        # 更新全局画风（使用最新的）
        global_style = focus.global_style

        all_results.append((focus, plot))

    return all_results

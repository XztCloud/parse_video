"""小说解析服务

把小说全文按章节切分为"每章节一个块"（SceneChunk），供后续LLM剧情分析使用。

不在此处做角色/场景/对话的规则识别——那部分不准确且下游没有任何代码消费，
角色库/场景库由 novel_analysis 的 LLM 从原文中抽取（focus/plot）。
这里只负责：
1. 章节检测（识别"第X章/序章/Chapter One"等标题）
2. 每章节产出1个 SceneChunk，估算其时长
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)

# 章节检测正则表达式（参考ai-novel2script的CHAPTER_HEADING_RE）
CHINESE_NUMBER = r"[一二三四五六七八九十百千万零〇两\d]+"
CHINESE_SPECIAL_HEADING = r"(?:序章|序幕|楔子|引子|终章|尾声|后记)"
ENGLISH_NUMBER = (
    r"\d+|[ivxlcdm]+|"
    r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
    r"thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|"
    r"twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
    r"(?:[-\s](?:one|two|three|four|five|six|seven|eight|nine))?"
)
ENGLISH_SPECIAL_HEADING = r"(?:prologue|epilogue)"

CHAPTER_HEADING_RE = re.compile(
    rf"""
    ^[^\S\n]*(?:\#{{1,6}}[^\S\n]*)?
    (?P<title>
        第[^\S\n]*{CHINESE_NUMBER}[^\S\n]*[章节回幕卷][^\n]*
        |{CHINESE_SPECIAL_HEADING}(?:[：:、.\-—][^\S\n]*.+|[^\S\n]+.+)?
        |(?:chapter|ch\.)\s+(?:{ENGLISH_NUMBER})(?=$|[\s:.\-—])[^\n]*
        |{ENGLISH_SPECIAL_HEADING}(?:[:.\-—][^\S\n]*.+)?
    )
    [^\S\n]*$
    """,
    re.IGNORECASE | re.MULTILINE | re.VERBOSE,
)

# 对话检测正则（用于时长估算）
DIALOGUE_RE = re.compile(r"(?P<speaker>[一-龥A-Za-z0-9_·]{1,16})[：:]\s*(?P<line>.+)")


@dataclass
class Chapter:
    """章节数据结构"""
    index: int
    title: str
    body: str


@dataclass
class SceneChunk:
    """章节块（一个章节对应一个SceneChunk）数据结构"""
    chapter_index: int
    chapter_title: str
    scene_index: int  # 恒为0，保留字段以兼容现有调用
    text: str
    char_count: int
    estimated_duration_seconds: float


def estimate_duration_seconds(text: str) -> float:
    """估算文本的时长（秒）

    只计算对话和旁白的时长，动作描写等视觉内容不占时间。
    参考：中文对话约4.5字/秒，旁白约4字/秒。

    Args:
        text: 文本内容

    Returns:
        预估时长（秒）
    """
    # 提取对话（格式：角色名：台词内容）
    dialogue_matches = DIALOGUE_RE.findall(text)
    dialogue_chars = sum(len(line) for _, line in dialogue_matches)

    # 提取旁白/内心独白（包含特定关键词的段落）
    inner_monologue_keywords = ["心想", "心里想", "内心", "暗想", "思考", "旁白"]
    paragraphs = text.split('\n\n')
    narration_chars = 0
    for paragraph in paragraphs:
        paragraph = paragraph.strip()
        if any(keyword in paragraph for keyword in inner_monologue_keywords):
            # 这是旁白/内心独白，计算字符数
            narration_chars += len(re.findall(r'[一-龥]', paragraph))

    # 计算总时长
    # 对话：4.5字/秒，旁白：4字/秒
    dialogue_duration = dialogue_chars / 4.5
    narration_duration = narration_chars / 4.0

    total_duration = dialogue_duration + narration_duration

    # 至少返回1秒（避免0时长）
    return max(1.0, total_duration)


def parse_chapters(text: str) -> list[Chapter]:
    """解析小说文本，提取章节

    Args:
        text: 小说文本

    Returns:
        章节列表

    Raises:
        ValueError: 如果未识别到章节标题
    """
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip().lstrip("﻿")
    if not cleaned:
        raise ValueError("输入文本为空，无法转换。")

    matches = list(CHAPTER_HEADING_RE.finditer(cleaned))
    if not matches:
        raise ValueError("未识别到章节标题，请使用'第X章'、'序章'或'Chapter One'等格式。")

    chapters: list[Chapter] = []
    for index, match in enumerate(matches, start=1):
        body_start = match.end()
        body_end = matches[index].start() if index < len(matches) else len(cleaned)
        title = _normalize_spaces(match.group("title"))
        body = cleaned[body_start:body_end].strip()
        if body:
            chapters.append(Chapter(index=len(chapters) + 1, title=title, body=body))

    return chapters


def parse_novel(file_path: str) -> tuple[str, list[Chapter], list[SceneChunk]]:
    """解析小说文件，返回完整文本、章节列表和章节块列表

    规则：每章节生成一个SceneChunk，不在此处做角色/场景/对话识别。

    Args:
        file_path: 小说文件路径

    Returns:
        (full_text, chapters, scene_chunks)
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        full_text = f.read()

    # 解析章节
    chapters = parse_chapters(full_text)

    # 每个章节生成1个场景块
    scene_chunks = [_create_scene_chunk(chapter) for chapter in chapters]

    return full_text, chapters, scene_chunks


def _create_scene_chunk(chapter: Chapter) -> SceneChunk:
    """根据章节创建SceneChunk（一个章节一个块）

    Args:
        chapter: 章节数据

    Returns:
        SceneChunk
    """
    return SceneChunk(
        chapter_index=chapter.index,
        chapter_title=chapter.title,
        scene_index=0,
        text=chapter.body,
        char_count=len(chapter.body),
        estimated_duration_seconds=estimate_duration_seconds(chapter.body),
    )


def _normalize_spaces(value: str) -> str:
    """规范化空白字符"""
    return re.sub(r"\s+", " ", value).strip()

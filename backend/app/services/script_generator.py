import json
from pathlib import Path
from typing import List, Literal, Optional
import logging
import re

import pandas as pd
from pydantic import BaseModel, Field
from ..config import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

logger = logging.getLogger(__name__)

RETRY_MAX=3

# 常见运镜/景别/拍摄特征关键词，用于从分镜描述文本中提取镜头特征标签
SHOT_FEATURE_KEYWORDS = [
    "特写", "近景", "中景", "全景", "远景", "大远景",
    "仰拍", "俯拍", "平视", "侧面", "背面", "主观视角",
    "推镜", "拉远", "拉镜", "跟拍", "升降", "环绕", "旋转",
    "慢动作", "快进", "延时", "定格", "淡入", "淡出",
    "转场", "蒙太奇", "手持", "稳定", "变焦", "对焦",
    "面部特写", "手部特写", "眼神特写", "慢镜头", "一镜到底",
]


def extract_shot_features(description) -> list[str]:
    """从分镜描述文本中启发式提取镜头特征标签（string list）。

    不做 LLM 调用，纯关键词匹配，返回去重后的有序标签；无匹配返回空列表。
    """
    if not description:
        return []
    text = str(description)
    found = []
    for kw in SHOT_FEATURE_KEYWORDS:
        if kw in text and kw not in found:
            found.append(kw)
    return found


# 视频类型候选集（与前端 tagPresets 对齐），用于类型归类
VIDEO_TAG_PRESETS = [
    "美食探店", "知识科普", "生活技巧", "情感语录", "旅行攻略",
    "数码测评", "健身教学", "宠物日常", "穿搭分享", "职场干货",
    "读书分享", "影视解说", "音乐翻唱", "手工DIY", "汽车评测",
    "母婴育儿", "家居好物", "游戏解说", "理财科普", "户外探险",
    "产品推广"
]

VIDEO_TYPE_PROMPT = """
你是一位短视频内容分类专家。请阅读下面这段视频脚本/分析内容，判断它属于哪一类视频，并给出一句话总结。

【候选分类】（必须且只能从下列标签中选择一个）：
{candidate_tags}

【视频脚本/分析内容】：
{script_content}

请严格按照如下 JSON 格式输出（不要输出任何其他文字、不要 Markdown 围栏）：
{{"category": "选中的分类标签", "summary": "一句话总结这段视频的核心内容（40字以内）"}}
"""

# LLM 生成镜头特征时可选的标签候选
SHOT_FEATURE_CANDIDATES = [
    "特写", "近景", "中景", "全景", "远景", "大远景",
    "仰拍", "俯拍", "平视", "侧面", "背面", "主观视角",
    "推镜", "拉远", "拉镜", "跟拍", "升降", "环绕", "旋转",
    "慢动作", "快进", "延时", "定格", "手持", "变焦",
]

SHOT_FEATURES_PROMPT = """
你是一位专业的短视频分镜导演。下面是一段视频的分镜脚本，每个分镜有【镜头描述】。

请为**每个分镜**挑选 2~4 个最贴切的【镜头特征标签】。标签必须从以下候选中选择，只能使用纯中文名词：
{candidates}

判定规则：
- 只看文字描述里能体现的运镜/景别/拍摄手法（如特写、全景、仰拍、慢动作、推镜等）；
- 没有明确体现的可少给（最少 1 个），不要编造；
- 严格按分镜顺序输出，数量与输入分镜数完全一致，一一对应。

【分镜脚本】：
{segments}

请严格按照如下 JSON 格式输出（不要输出任何其他文字、不要 Markdown 围栏），
"features" 是一个二维数组，第 i 个元素对应第 i 个分镜的标签列表：
{{"features": [["特写", "慢动作"], ["全景"], ...]}}
"""

def convert_markdown_title(text, title="剧情脚本"):
    """统计字符串中第一次出现的连续 # 个数"""
    match = re.search(r'#+', text)

    level = len(match.group()) if match else 0
    
    if not 1 <= level <= 6:
        return ''
    
    hashes = '#' * level
    return f"{hashes} {title}"

def split_by_time_window(
    items: list[dict],
    window_ms: int = 60_000,
    time_key: str = "start_time",
) -> list[list[dict]]:
    """
    将 list[dict] 按照 start_time 所在的时间窗口进行分段。

    时间窗口以 0 为起点，每 window_ms 毫秒为一个窗口：
        [0, 60000), [60000, 120000), [120000, 180000), ...

    每条数据根据其 start_time 落入对应窗口，同一窗口内的数据归入同一个
    list[dict]，最终输出 list[list[dict]]，每个子列表按 start_time 升序排列。

    Args:
        items:     待分段的数据列表，每条 dict 必须包含 time_key 指定的字段。
        window_ms: 时间窗口长度（毫秒），默认 60000（1 分钟）。
        time_key:  用作分段依据的时间字段名，默认 "start_time"。

    Returns:
        分段后的 list[list[dict]]，按窗口起始时间升序排列。

    Examples:
        >>> data = [
        ...     {"start_time": 240,   "text": "A"},
        ...     {"start_time": 1720,  "text": "B"},
        ...     {"start_time": 7000,  "text": "C"},
        ...     {"start_time": 62000, "text": "D"},   # 落入第2个窗口
        ... ]
        >>> split_by_time_window(data)
        [
            [{"start_time": 240, "text": "A"},
             {"start_time": 1720, "text": "B"},
             {"start_time": 7000, "text": "C"}],
            [{"start_time": 62000, "text": "D"}]
        ]
    """
    if not items:
        return []

    # 按 start_time 排序，保证有序
    sorted_items = sorted(items, key=lambda x: x[time_key])

    # 用 dict 收集各窗口的数据，key 为窗口索引
    buckets: dict[int, list[dict]] = {}
    for item in sorted_items:
        t = item[time_key]
        # 兼容秒级浮点数（如 4.0 秒 = 4000 毫秒）
        if isinstance(t, float) and t < 1000:
            t = t * 1000
        window_idx = int(t // window_ms)
        buckets.setdefault(window_idx, []).append(item)

    # 按窗口索引升序输出
    return [buckets[k] for k in sorted(buckets.keys())]


def find_outermost_list(data):
    """
    自动寻找 JSON 结构中最外层的 list。
    如果本身是 list 则直接返回；如果是 dict，则寻找第一个遇到的 list。
    """
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        # 优先在当前层级寻找 list 类型的 value
        for value in data.values():
            if isinstance(value, list):
                return value
        # 如果当前层没找到，递归向更深层 dict 寻找
        for value in data.values():
            if isinstance(value, dict):
                result = find_outermost_list(value)
                if result is not None:
                    return result
    return None


def json_item_to_markdown(item, level=0):
    """
    递归处理 List 内部的每一个元素，将其转换为带缩进的文本
    """
    md_content = ""
    indent = "  " * level
    
    if isinstance(item, dict):
        for key, value in item.items():
            if isinstance(value, (dict, list)):
                md_content += f"{indent}- **{key}**:\n"
                md_content += json_item_to_markdown(value, level + 1)
            else:
                md_content += f"{indent}- **{key}**: {value}\n"
    elif isinstance(item, list):
        for sub_item in item:
            md_content += json_item_to_markdown(sub_item, level)
    else:
        md_content += f"{indent}- {item}\n"
        
    return md_content


def convert_markdown(ori_data: json) -> str:
    target_list = find_outermost_list(ori_data)
    markdown_text = ""

    if target_list is None:
        print("❌ 错误：在 JSON 中未找到任何 List (数组) 结构！")
        markdown_text = ori_data
    else:
        reset_title_list = []
        for index, item in enumerate(target_list):
            print(f'Item {index}: {item}')
            print(f'Type of Item {index}: {type(item)}')
            dialogue = item.get('dialogue', [])
            item['dialogue'] = "  ".join(f"{d['speaker']}:{d['text']}" for d in dialogue)
            print(f'Processed dialogue for Item {index}: {item["dialogue"]}, type: {type(item["dialogue"])}')
            reset_item = {}
            if item.get('start_time') is not None:
                item['start_time'] = round(item['start_time'] / 1000, 1)
                reset_item['开始'] = item['start_time']
            if item.get('end_time') is not None:
                item['end_time'] = round(item['end_time'] / 1000, 1)
                reset_item['结束'] = item['end_time']
            if item.get('plot_tag') is not None:
                reset_item['段落主题'] = item['plot_tag']
            if item.get('shot_description') is not None:
                reset_item['镜头描述'] = item['shot_description']
            if item.get('dialogue') is not None:
                reset_item['对话'] = item['dialogue']
            if reset_item:
                reset_title_list.append(reset_item)
                
        
        reset_title_list = reset_title_list if reset_title_list else target_list
        df = pd.DataFrame(reset_title_list)
        # index=False 表示不把行索引（0, 1, 2...）写进表格
        df = df.replace(r'\|', r'\|', regex=True)
        markdown_table = df.to_markdown(index=False)
        return markdown_table


# ===== summary_script 结构化输出模型（严格对齐 llm.py CloneAnalysisFocus / CloneAnalysisPlot）=====

from app.services.llm import (
    CharacterInfo, SceneDetail, SceneStyleGlobal, CoreSellingPoint,
    CloneAnalysisFocus, ActorLines, ClonePlotScript, CloneAnalysisPlot,
)

SummaryFocusOutput = CloneAnalysisFocus
SummaryPlotOutput = CloneAnalysisPlot


class VideoTypeOutput(BaseModel):
    """视频类型总结输出"""
    category: str = Field(description="视频分类标签")
    summary: str = Field(description="一句话总结")


def _focus_to_markdown(focus: SummaryFocusOutput) -> str:
    """将 SummaryFocusOutput 转为 markdown 分析文本。"""
    lines = []
    lines.append("## 角色列表\n")
    for r in focus.role_library:
        voice_info = f"，声音风格：{r.voice_style_guide}" if r.voice_style_guide else ""
        lines.append(f"- **{r.role_name}**（{r.gender}，约{r.age}岁{voice_info}）：{r.effect}")
    lines.append("")
    lines.append("## 场景列表\n")
    for s in focus.scene_library:
        lines.append(f"- **{s.scene_name}**：{s.environment_description}")
        if s.color_grading:
            lines.append(f"  - 调色：{s.color_grading}")
    lines.append("")
    lines.append(f"## 全局画风\n\n{focus.global_style.global_style_suffix}\n")
    if focus.core_shell_point:
        sp = focus.core_shell_point
        lines.append("## 核心卖点\n")
        if sp.user_pain_point:
            lines.append(f"- 用户痛点：{sp.user_pain_point}")
        if sp.product_usp:
            lines.append(f"- 产品卖点：{'；'.join(sp.product_usp)}")
        if sp.hook_trigger:
            lines.append(f"- 钩子：{sp.hook_trigger}")
        if sp.keywords_to_include:
            lines.append(f"- 关键词：{'、'.join(sp.keywords_to_include)}")
    return "\n".join(lines)


class ScriptGenerator:
    @staticmethod
    async def generate_script(asr_segments: list[dict], visual_segments: list[dict]) -> list:
        asr_segments = sorted(asr_segments, key=lambda x: x['start_time'])
        asr_cnt = 0
        for visual in visual_segments:
            visual['start_time'] = float(visual['start_time'])
            visual['end_time'] = float(visual['end_time'])
            visual['dialogue'] = []
            while asr_cnt < len(asr_segments) and ((asr_segments[asr_cnt]['start_time'] + asr_segments[asr_cnt]['end_time']) / 2) < visual['end_time']:
                visual['dialogue'].append({
                    'start_time': asr_segments[asr_cnt]['start_time'], 
                    'end_time': asr_segments[asr_cnt]['end_time'],
                    'speaker':asr_segments[asr_cnt]['speaker'], 
                    'text': asr_segments[asr_cnt]['text']
                })
                asr_cnt += 1
        print(f'visual_segments: {visual_segments}')
        return visual_segments


    @staticmethod
    async def llm_generate_script(asr_segments: list[dict], visual_segments: list[dict]) -> list:

        json_example = """
[{
    "start_time": 128000.0,
    "end_time": 132000.0,
    "shot_description": "片段1的描述",
    "dialogue": [
        {"speaker": "2", "text": "哦。"},
        {"speaker": "2", "text": "随便看，我也不知道吃什么。"},
        {"speaker": "3", "text": "又是老问题，中午吃啥？"}
    ],
    "segment_type": "mixed"
},
{
    "start_time": 132000.0,
    "end_time": 136000.0,
    "shot_description": "片段2的描述",
    "dialogue": [
        {"speaker": "2", "text": "别急，我找个人问问。"}
    ],
    "segment_type": "mixed"
}]
"""

        prompt = f"""
你是专业视频脚本分析师。将以下语音识别和镜头分析结果整合为结构化视频脚本。

语音识别结果（带时间戳）：{asr_segments}
镜头分析结果（带时间戳）：{visual_segments}

根据语音识别结果和镜头分析结果，可以根据你的经验适当合并镜头，简化描述，使结果更加简明流畅。

输出JSON格式脚本，每个片段包含：start_time, end_time, shot_description, dialogue(包含{{'speaker':'1', 'text': '...'}}组成的list), segment_type(shot/dialogue/mixed)。按时间顺序合并，时间连续不重叠。
输出示例：
{json_example}
"""
        
        model_name=settings.LLM_NAME
        base_url=settings.LLM_BASE_URL
        api_key=settings.LLM_API_KEY

        llm_kwargs = {
            "model": model_name,
            "temperature": 0.3,
            "max_tokens": 20480
        }
        if api_key:
            llm_kwargs["api_key"] = api_key
        if base_url:
            llm_kwargs["base_url"] = base_url

        llm = ChatOpenAI(**llm_kwargs)

        messages = [SystemMessage(content=prompt)]
        
        result = []
        last_start_time = max(item['start_time'] for item in visual_segments)
        cnt = 0
        
        while cnt * 60_000 <= last_start_time:
            item_last_start_time = min((cnt+1) * 60_000, last_start_time+1)
            query = f'以start_time为标准，将指定的时间段内（{cnt * 60_000}<=start_time<{item_last_start_time}）的数据，按照指定格式输出json。要json.loads可以解析，不要添加```json```等其他字符'
            retry = 0
            messages.append(HumanMessage(content=query))
            while retry < RETRY_MAX:
                response = llm.invoke(messages)
                content = response.content.strip()
                print(f'content: {content}')
                
                try:
                    result += json.loads(content)
                    break
                except json.JSONDecodeError as e:
                    messages.append(AIMessage(content=content))
                    messages.append(HumanMessage(content=f'json.JSONDecodeError, error is {e}, 重新生成结果让json.load可以解析。'))
                    print(f'json.JSONDecodeError: {e}')
                    retry += 1
                except Exception as e:
                    print(f'Exception: {e}')
                    retry = RETRY_MAX
            if retry == RETRY_MAX:
                print('retry count reached RETRY_MAX! failed.')
                return []

            cnt += 1
        print(f'result: {result}, result type: {type(result)}')

        return result


    @staticmethod
    async def enhance_shot_descriptions(script_result: list[dict]) -> list[dict]:
        """结合画面描述和对话，为每个分镜生成更完整、更生动的 shot_description。

        输出格式参考 llm.py 中 StoryBoard 的 prompt_for_video：
        具体场景、动作、景别的导演描述，可直接用于 AI 生图/生视频。
        """
        if not script_result:
            return script_result

        model_name = settings.LLM_NAME
        base_url = settings.LLM_BASE_URL
        api_key = settings.LLM_API_KEY

        llm_kwargs = {
            "model": model_name,
            "temperature": 0.3,
            "max_tokens": 4096,
        }
        if api_key:
            llm_kwargs["api_key"] = api_key
        if base_url:
            llm_kwargs["base_url"] = base_url

        llm = ChatOpenAI(**llm_kwargs)

        # 构造分镜摘要给 LLM
        segment_summary = []
        for i, seg in enumerate(script_result):
            dialogue_texts = []
            for d in seg.get('dialogue', []):
                dialogue_texts.append(f"角色{d.get('speaker', '未知')}: {d.get('text', '')}")
            segment_summary.append({
                "index": i,
                "shot_description": seg.get('shot_description', ''),
                "dialogue": dialogue_texts,
                "segment_type": seg.get('segment_type', 'mixed'),
            })

        prompt = f"""你是一位专业的短视频分镜导演。请根据每个分镜的【画面描述】和【对话内容】，为每个分镜生成一段更完整、更生动的分镜描述。

【输出格式要求】
每个分镜输出为纯文本描述，参考以下示例：
- 示例1：中景推镜，现代办公室内景，办公桌，电脑，员工背影，镜头从门口缓缓推进，穿过格子间。
- 示例2：人物特写，一位30岁的亚洲女性老板双手猛拍桌子，怒不可遏，坐在她对面的25岁男性程序员神情紧张。
- 示例3：全景，温馨卧室，暖黄色灯光，柔和窗帘，阳光洒落，镜头从天花板缓缓下降。

描述要求：
1. 包含：景别（全景/中景/近景/特写等）、镜头运动（推镜/拉镜/跟拍/固定等）、画面主体、环境细节、光影氛围
2. 结合对话内容补充分镜中的人物动作、情绪
3. 描述要具体、可执行，便于后续AI生图/生视频
4. 保持与原描述一致的时间线和场景逻辑
5. 每个分镜输出一段纯文本，不要JSON格式

【分镜信息】
{json.dumps(segment_summary, ensure_ascii=False, indent=2)}

请按顺序为每个分镜输出增强后的描述，每个分镜之间用"---"分隔："""

        for attempt in range(RETRY_MAX):
            try:
                messages = [SystemMessage(content=prompt)]
                response = llm.invoke(messages)
                content = response.content.strip()

                # 按 "---" 分割各分镜描述
                enhanced_parts = [p.strip() for p in content.split('---') if p.strip()]

                if len(enhanced_parts) >= len(script_result):
                    for i, desc in enumerate(enhanced_parts[:len(script_result)]):
                        script_result[i]['shot_description'] = desc
                    logger.info(f'enhance_shot_descriptions: 成功增强 {len(enhanced_parts)} 个分镜描述')
                    return script_result
                else:
                    logger.warning(f'enhance_shot_descriptions: 返回 {len(enhanced_parts)} 段，期望 {len(script_result)} 段，重试')
                    continue
            except Exception as e:
                logger.error(f'enhance_shot_descriptions attempt {attempt + 1} failed: {e}')
                continue

        logger.error('enhance_shot_descriptions: 所有重试失败，保持原始描述')
        return script_result


    @staticmethod
    async def summary_script(script_result: list[dict], output_dir: str | Path) -> list:
        """分析分镜脚本并合并为剧情段落。

        两步流程（参照 llm.py creative_model_focus / creative_model_plot）：
        1. 分析焦点：提取角色、场景、卖点 → SummaryFocusOutput
        2. 合并剧情：将分镜合并为剧情段落 → SummaryPlotOutput

        返回格式兼容 parse_video.py：
        result[0] = markdown 分析文本（存入 parse_pointer）
        result[1] = plot_script JSON（存入 parse_script）
        result[2] = markdown 表格（写入文件）
        result[3] = 文件路径（存入 parse_file_path）
        """
        folder_path = Path(output_dir)
        folder_path.mkdir(parents=True, exist_ok=True)

        model_name = settings.LLM_NAME
        base_url = settings.LLM_BASE_URL
        api_key = settings.LLM_API_KEY

        llm_kwargs = {
            "model": model_name,
            "temperature": 0.3,
            "max_tokens": 20480,
        }
        if api_key:
            llm_kwargs["api_key"] = api_key
        if base_url:
            llm_kwargs["base_url"] = base_url

        llm = ChatOpenAI(**llm_kwargs)

        # ===== 第一步：分析焦点（对标 creative_model_focus）=====
        focus_system = """你是一位专业的短视频导演，精通分析借鉴热门短视频脚本。
请分析以下分镜脚本，提取角色、场景、全局画风和核心卖点信息。
【重要】注意识别视频中推广的产品/品牌/服务——即使以创意剧情形式呈现，只要出现了品牌名、产品名、宣传语或产品展示画面，都属于推广内容，必须提取到核心卖点中。"""

        focus_query = f"""以下是待分析的短视频分镜脚本：

{json.dumps(script_result, ensure_ascii=False, indent=2)}

请分析出：
1. 角色列表（role_name, gender, age, voice_style_guide, effect）
   【重要】如果分镜中存在旁白/画外音/广告语配音，必须在角色列表中添加一个旁白角色（如"旁白"或"广告旁白"），gender 填 male，age 填 30，effect 填"旁白/画外音"。缺少旁白角色会导致后续流程报错。
2. 场景列表（scene_name, environment_description, color_grading）
3. 全局画风（global_style_suffix：生图后缀，中文提示词）
4. 核心卖点——特别注意：
   - 用户痛点是什么？
   - 产品卖点/USP
   - 钩子/Hook（吸引观众的前3秒设计）
   - 品牌关键词（必须出现的词）"""

        focus_model = llm.with_structured_output(SummaryFocusOutput)
        focus_result = None
        for attempt in range(RETRY_MAX):
            try:
                focus_result = focus_model.invoke([
                    SystemMessage(content=focus_system),
                    HumanMessage(content=focus_query),
                ])
                logger.info(f'summary_script focus: roles={len(focus_result.role_library)}, scenes={len(focus_result.scene_library)}')
                break
            except Exception as e:
                logger.warning(f'summary_script focus attempt {attempt + 1} failed: {e}')
                if attempt == RETRY_MAX - 1:
                    focus_result = CloneAnalysisFocus(role_library=[], scene_library=[], global_style={"global_style_suffix": ""}, core_shell_point=None)

        # 将 focus 转为 dict（存入 parse_pointer jsonb 列，格式对齐 clone_parse_pointer）
        focus_json = focus_result.model_dump()

        # ===== 第二步：合并剧情段落（对标 creative_model_plot）=====
        plot_system = """你是一位严谨的短视频分镜导演。请将以下分镜列表合并为剧情段落。
合并规则：相邻且关联紧密的分镜合并为一段。
【重要】必须保留每个段落的 start_time 和 end_time，从原始分镜数据中继承。"""

        plot_query = f"""以下是分镜列表：

{json.dumps(script_result, ensure_ascii=False, indent=2)}

请合并为剧情段落列表。每个段落包含：
- start_time/end_time：从原始分镜继承，不能为0
- paragraph_theme：本段主题一句话概括
- screen_description：导演向的画面描述
- actor_lines：台词列表，每项包含 role_name、predict_duration（秒）、lines（台词文本）、audio_style（语气描述）

原始分镜中的对话格式：{{speaker: "角色编号", text: "台词"}}，请转为 actor_lines 格式。"""

        plot_model = llm.with_structured_output(SummaryPlotOutput)
        plot_result = None
        for attempt in range(RETRY_MAX):
            try:
                plot_result = plot_model.invoke([
                    SystemMessage(content=plot_system),
                    HumanMessage(content=plot_query),
                ])
                logger.info(f'summary_script plot: {len(plot_result.plot_script)} segments')
                break
            except Exception as e:
                logger.warning(f'summary_script plot attempt {attempt + 1} failed: {e}')
                if attempt == RETRY_MAX - 1:
                    # fallback：直接用原始 script_result
                    plot_result = CloneAnalysisPlot(plot_script=[
                        ClonePlotScript(
                            start_time=s.get('start_time', 0) / 1000 if s.get('start_time', 0) > 1000 else s.get('start_time', 0),
                            end_time=s.get('end_time', 0) / 1000 if s.get('end_time', 0) > 1000 else s.get('end_time', 0),
                            paragraph_theme=s.get('shot_description', '')[:50],
                            screen_description=s.get('shot_description', ''),
                            actor_lines=[
                                ActorLines(
                                    role_name=f"角色{d.get('speaker', '未知')}",
                                    predict_duration=(d.get('end_time', 0) - d.get('start_time', 0)) / 1000 if d.get('end_time', 0) > 1000 else 3.0,
                                    lines=d.get('text', ''),
                                    audio_style="自然"
                                ) for d in s.get('dialogue', [])
                            ],
                        ) for s in script_result
                    ])

        # 将 plot 转为 JSON（存入 parse_script）
        plot_json = [item.model_dump() for item in plot_result.plot_script]

        # 兜底：如果 LLM 没填时间，从原始分镜补
        for p in plot_json:
            if p.get('start_time', 0) == 0 and p.get('end_time', 0) == 0:
                # 找第一个匹配的原始分镜
                for seg in script_result:
                    if seg.get('shot_description', '')[:30] in p.get('screen_description', ''):
                        p['start_time'] = seg.get('start_time', 0) / 1000 if seg.get('start_time', 0) > 1000 else seg.get('start_time', 0)
                        p['end_time'] = seg.get('end_time', 0) / 1000 if seg.get('end_time', 0) > 1000 else seg.get('end_time', 0)
                        break

        # 生成 markdown 表格
        markdown_data = convert_markdown(plot_json)

        # 写入文件
        file_path = folder_path / 'parse_video.md'
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(focus_json, ensure_ascii=False))
            f.write(f"\n\n## 分镜脚本\n\n")
            f.write(markdown_data)

        result = [focus_json, plot_json, markdown_data, str(file_path.absolute())]
        return result

    @staticmethod
    async def summary_video_type(script_content, candidate_tags: list[str] | None = None) -> dict:
        """对视频脚本做类型归类 + 一句话总结。

        Args:
            script_content: 解析出的脚本内容（markdown 或 json 文本）。
            candidate_tags: 候选类型标签列表；为空时使用默认 VIDEO_TAG_PRESETS。

        Returns:
            {"category": str, "summary": str}；失败时 category="未知分类", summary=""。
        """
        import json as _json

        tags = candidate_tags or VIDEO_TAG_PRESETS
        if not script_content:
            return {"category": "未知分类", "summary": ""}

        try:
            model_name = settings.LLM_NAME
            base_url = settings.LLM_BASE_URL
            api_key = settings.LLM_API_KEY

            llm_kwargs = {
                "model": model_name,
                "temperature": 0.2,
                "max_tokens": 1024,
            }
            if api_key:
                llm_kwargs["api_key"] = api_key
            if base_url:
                llm_kwargs["base_url"] = base_url

            llm = ChatOpenAI(**llm_kwargs)
            content_preview = str(script_content)[:4000]
            user_prompt = VIDEO_TYPE_PROMPT.format(
                candidate_tags="、".join(tags),
                script_content=content_preview,
            )

            last_err = None
            for _attempt in range(RETRY_MAX):
                try:
                    response = llm.invoke([HumanMessage(content=user_prompt)])
                    raw = str(response.content).strip()
                    logger.debug(f'summary_video_type response.content type={type(response.content)}, value={str(response.content)[:300]}')
                    if not raw:
                        raise ValueError(f"empty LLM response, raw type={type(response.content)}, repr={repr(response.content)[:300]}")
                    # 剥离可能的 markdown 围栏
                    if raw.startswith("```"):
                        lines = raw.split("\n", 1)
                        raw = lines[1] if len(lines) > 1 else raw
                        raw = raw.rstrip()
                        if raw.endswith("```"):
                            raw = raw[:-3].strip()
                    data = _json.loads(raw)
                    category = data.get("category") if isinstance(data, dict) else ""
                    summary = data.get("summary") if isinstance(data, dict) else ""
                    if not isinstance(category, str) or category not in tags:
                        category = ""
                    if not isinstance(summary, str):
                        summary = ""
                    return {"category": category or "未知分类", "summary": summary or ""}
                except Exception as e:
                    last_err = e
                    logger.warning(f'summary_video_type attempt {_attempt + 1} failed: {e}')
            raise last_err
        except Exception as e:
            logger.error(f'summary_video_type failed: {e}')
            return {"category": "未知分类", "summary": ""}

    @staticmethod
    async def generate_shot_features(segments: list[dict]) -> list[list[str]]:
        """为每个分镜生成镜头特征标签列表（特写/慢动作/全景等）。

        一次 LLM 批量调用，输入所有分镜描述，返回与 segments 一一对应的
        list[list[str]]；失败或长度不符时返回 []，由调用方回退关键词提取。
        """
        if not segments:
            return []
        try:
            model_name = settings.LLM_NAME
            base_url = settings.LLM_BASE_URL
            api_key = settings.LLM_API_KEY

            llm_kwargs = {
                "model": model_name,
                "temperature": 0.2,
                "max_tokens": 2048,
            }
            if api_key:
                llm_kwargs["api_key"] = api_key
            if base_url:
                llm_kwargs["base_url"] = base_url

            llm = ChatOpenAI(**llm_kwargs)

            seg_preview = json.dumps(
                [
                    {"index": i, "shot_description": str(s.get("shot_description", ""))[:150]}
                    for i, s in enumerate(segments)
                ],
                ensure_ascii=False,
            )
            user_prompt = SHOT_FEATURES_PROMPT.format(
                candidates="、".join(SHOT_FEATURE_CANDIDATES),
                segments=seg_preview,
            )

            last_err = None
            for _attempt in range(RETRY_MAX):
                try:
                    response = llm.invoke([HumanMessage(content=user_prompt)])
                    raw = str(response.content).strip()
                    logger.debug(f'generate_shot_features response.content type={type(response.content)}, value={str(response.content)[:300]}')
                    if not raw:
                        raise ValueError(f"empty LLM response, raw type={type(response.content)}, repr={repr(response.content)[:300]}")
                    if raw.startswith("```"):
                        lines = raw.split("\n", 1)
                        raw = lines[1] if len(lines) > 1 else raw
                        raw = raw.rstrip()
                        if raw.endswith("```"):
                            raw = raw[:-3].strip()
                    data = json.loads(raw)
                    features = data.get("features") if isinstance(data, dict) else None
                    if not isinstance(features, list):
                        raise ValueError(f"bad features: {str(raw)[:200]}")
                    result = []
                    for f in features:
                        if isinstance(f, list):
                            result.append([str(x) for x in f if x])
                        else:
                            result.append([])
                    if len(result) != len(segments):
                        raise ValueError(
                            f"features count {len(result)} != segments {len(segments)}"
                        )
                    return result
                except Exception as e:
                    last_err = e
                    logger.warning(f'generate_shot_features attempt {_attempt + 1} failed: {e}')
            raise last_err
        except Exception as e:
            logger.error(f'generate_shot_features failed: {e}')
            return []




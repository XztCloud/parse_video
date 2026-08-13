import json
from typing import List, Literal, Optional

from celery.utils.log import get_task_logger
from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from app.config import settings

logger = get_task_logger(__name__)

model = init_chat_model(
    settings.LLM_NAME,
    temperature = 0.7,
    model_provider='openai',
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
    configurable_fields=("model", "temperature")
)

#节点A##########################################################################################################
class CharacterInfo(BaseModel):
    role_name: str = Field(
        ...,
        description="角色在剧本中的唯一名称。例如：'女高管'、'男程序员'、'旁白'。"
    )
    gender: Literal['male', 'female'] = Field(description="角色的性别。")
    age: int = Field(description="角色的具体年龄或大致年龄段（如 25），用于控制 TTS 的声音成熟度和生图的年龄感。")
    voice_style_guide: Optional[str] = Field(
        default=None,
        description="大模型对该角色声音风格的建议描述。例如：'声音低沉、带有磁性、语速中等'。如果没有台词，则不填。"
    )
    effect: str = Field(
        ...,
        description="该角色在剧本中的作用"
    )
    

class SceneDetail(BaseModel):
    """
    单个独立场景的画风与环境定义。
    """
    scene_name: str = Field(
        ..., 
        description="场景的唯一标识名称。例如：'深夜办公室'、'温馨卧室'、'喧闹咖啡厅'。"
    )
    
    environment_description: str = Field(
        ..., 
        description="该场景的详细环境和画风描述。例如：'昏暗的写字楼工位，百叶窗外有微弱的城市霓虹灯光，桌上堆满咖啡罐'。"
    )
    
    color_grading: str = Field(
        ..., 
        description="该场景专属的调色风格。例如：'冷蓝色，高对比度'（用于深夜办公室），'暖黄色，柔和'（用于卧室）。"
    )

class SceneStyleGlobal(BaseModel):
    """
    全局视觉母模板，保证换了场景但电影质感（画幅、相机、画风种子）不穿帮。
    """
    global_style_suffix: str = Field(
        ..., 
        description="全局通用的生图后缀。全局视觉母模板，保证换了场景但电影质感（画幅、相机、画风种子）不穿帮。中文提示词"
    )

class CoreSellingPoint(BaseModel):
    """
    核心卖点与营销痛点模型，用于锁定剧本的商业逻辑，防止 AI 偏离推广主题。
    """
    user_pain_point: str = Field(
        ..., 
        description="新主题下目标用户的核心痛点。例如：'想接入 AI 提效，但多模型 API 切换和代码重构太痛苦'。"
    )
    
    product_usp: List[str] = Field(
        ..., 
        description="产品/新主题的独家竞争优势（Unique Selling Proposition）。例如：['统一 API 接入点，零代码破坏无缝切换模型', '价格便宜，百万token才0.01元']。"
    )
    
    hook_trigger: str = Field(
        ..., 
        description="黄金3秒的抓人钩子（Hook）核心概念。例如：'用深夜加班改重构代码的崩溃场景引发精准共鸣'。"
    )
    
    keywords_to_include: List[str] = Field(
        ..., 
        description="新台词中**必须强行出现**的品牌词或核心关键词列表。例如：['火山引擎', 'Ark平台', '零重构']。"
    )
    
class ActorLines(BaseModel):
    role_name: str = Field(..., description="角色在剧本中的唯一名称。一定要使用已经创建的角色，且角色名要一致")
    predict_duration: float = Field(..., ge=0.0, description='台词预估时长，单位秒。每段剧情中所有台词的predict_duration之和要小于等于 end_time-start_time')
    lines: str = Field(..., description="角色台词， 中文约4.5个字每秒，英文约3.7个字母每秒")
    audio_style: str = Field(
        ...,
        description=(
            "TTS（语音合成）提示词修饰语。用于精确控制该段台词的发音情绪与声音状态。"
            "【编写规则】："
            "1. 必须使用简练的‘标签化词群’，用斜杠‘/’分隔，总字数控制在 15 字以内。"
            "2. 必须包含：核心情感（如：愤怒/悲伤/戏谑）+ 语调（如：低沉平稳/激昂）+ 空间环境（如：内心独白/隔墙喊叫/电话音质）。"
            "3. 严禁使用‘符合剧情’、‘看情况定’等模糊词汇。"
            "【正确示例】：'冷酷/嘲讽'、'专业沉稳/职场播音腔'、'内心独白/压抑/低沉混响'、'惊恐/高分贝/喘息声'。"
        )
    )

class ClonePlotScript(BaseModel):
    start_time: float = Field(
        ...,
        description="剧情段落开始时间，单位秒"
    )
    end_time: float = Field(
        ...,
        description="剧情段落结束时间，单位秒"
    )
    paragraph_theme: str = Field(
        ...,
        description="本段剧情的主要作用，一句话概括"
    )
    screen_description: str = Field(
        ...,
        description="该剧情片段的画面描述，导演向的画面导演词/分镜画面文学描述"
    )
    actor_lines: List[ActorLines] = Field(
        ...,
        description="本段剧情的台词信息"
    )
    
class CloneAnalysisFocus(BaseModel):
    role_library: list[CharacterInfo] = Field(description="视频中所有出镜或配音角色的结构化列表。")
    scene_library: List[SceneDetail] = Field(
        ..., 
        description="本片中所有可能用到的场景库列表。"
    )
    global_style: SceneStyleGlobal = Field(
        ..., 
        description="全局画风母模板约束。"
    )
    core_shell_point: CoreSellingPoint = Field(
        ...,
        description="核心卖点与营销痛点模型，用于锁定剧本的商业逻辑"
    )
    
class CloneAnalysisPlot(BaseModel):
    plot_script: List[ClonePlotScript] = Field(
        ...,
        description="新视频的剧情大纲"
    )

class CloneAnalysis(CloneAnalysisFocus, CloneAnalysisPlot):
    pass
    # role_library: list[CharacterInfo] = Field(description="视频中所有出镜或配音角色的结构化列表。")
    # scene_library: List[SceneDetail] = Field(
    #     ..., 
    #     description="本片中所有可能用到的场景库列表。"
    # )
    # global_style: SceneStyleGlobal = Field(
    #     ..., 
    #     max_length= 128,
    #     description="全局画风母模板约束。"
    # )
    # core_shell_point: CoreSellingPoint = Field(
    #     ...,
    #     description="核心卖点与营销痛点模型，用于锁定剧本的商业逻辑"
    # )
    # plot_script: List[ClonePlotScript] = Field(
    #     ...,
    #     description="新视频的剧情大纲"
    # )
    

CREATIVE_SYSTEM_PROMPT = """
# Role

你是一位精通微短剧和信息流广告（Feeds AI）的资深多模态创意总监。你擅长逆向拆解爆款视频的“骨架底层逻辑”，并将其完美重组到全新的商业主题中。

# Task

分析用户提供的输入，在保持原视频“黄金3秒、核心冲突、情绪节奏、痛点切入点”完全一致的前提下，进行宏观创意换血。

# Rules & Constraints

- 创意对齐：新大纲的每一个情节转折，必须严格对应原视频的节奏骨架。
- 严禁具体分镜：此阶段严禁输出“镜头 1、镜头 2”等详细分镜表格，只做宏观剧情和创意设定的输出。
- 每段剧情中台词的预估时长（predict_duration）之和要小于等于当前剧情的end_time-start_time。
"""

CREATIVE_QUERY_PROMPT = """
分析用户提供的【原视频分析文本】与【全新主题梗概】，在保持原视频“黄金3秒、核心冲突、情绪节奏、痛点切入点”完全一致的前提下，进行宏观创意换血。

1. 【原视频分析文本】
```Markdown
{analysis_focus}
```

2. 【全新主题梗概】
```Text
{clone_theme}
```

3. 【上次失败经验】（可能为空）：
```Text
{error_message}
```

请开始你的创意创作：
"""

CREATIVE_PLOT_QUERY_PROMPT = """
分析用户提供的 【原视频剧情大纲】按照【全新视频脚本】进行创意换血，输出新的视频大纲，保证新大纲符合【全新视频脚本】。

1. 【原视频剧情大纲】
```Json
{ori_plot}
```

2. 【全新视频脚本】
```Json
{new_plot_focus}
```

请开始你的创意创作：
"""


# RESET_LINES_PROMPT = """
# 请检查上述输出结构中 plot_script 每个元素。
# 确保 actor_lines
# """

creative_model_focus = model.with_structured_output(CloneAnalysisFocus)
creative_model_plot = model.with_structured_output(CloneAnalysisPlot)
# 防止输出格式出错
creative_model_focus_strict = model.with_structured_output(CloneAnalysisFocus, strict=True)
creative_model_plot_strict = model.with_structured_output(CloneAnalysisPlot, strict=True)


#节点B##########################################################################################################

class AudioTimeline(BaseModel):
    role_name: str = Field(
        ..., 
        description="发声角色名称。必须严格与输入 role_library 中的 role_name 保持完全一致，禁止自行发明角色名。"
    )
    lines: str = Field(
        ..., 
        description="在当前分镜中实际发声的台词文本。若台词跨分镜被截断，写完整句台词。"
    )
    audio_style: str = Field(
        ...,
        description="台词语气，必须与输入字段一致，不要修改"
    )
    lines_flag: Literal['head', 'body', 'tail', 'all'] = Field(
        ..., 
        description=(
            "完整句台词在当前分镜的承载状态。当一句话跨越 >=3 个分镜时中间分镜必用 body。"
            "head: 跨镜长台词的【起始段】。台词在本分镜开始，但本分镜结束时未读完；"
            "body: 跨镜长台词的【中间段】。台词在进入本分镜前已开始，且在本分镜结束时仍未读完（纯声音过客）；"
            "tail: 跨镜长台词的【收尾段】。台词在进入本分镜前已开始，并在本分镜内完整结束；"
            "all: 独立台词。该句台词在本分镜内开始并结束，不涉及前后跨镜。"
        )
    )
    start_offset: float = Field(
        ..., 
        description="台词在当前分镜时间线上的相对开始时间（单位：秒）。必须 >= 0 且 <= 当前分镜总时长。若台词从上一镜延续过来（tail），此处通常为 0.0。"
    )
    end_offset: float = Field(
        ..., 
        description="台词在当前分镜时间线上的相对结束时间（单位：秒）。min(start_offset+本地台词的predict_duration, start_offset+本分镜时长)"
    )

class SegmentRoleView(BaseModel):
    role_name: str = Field(
        ..., 
        description="角色名称。必须严格与输入 role_library 中的 role_name 保持完全一致，禁止自行发明角色名。"
    )
    visibility: Literal[
        "visible",
        "partial",
        "invisible"
    ] = Field(
        ...,
        description="人物在画面中的可见状态"
    )

    position: str = Field(
        ...,
        description="人物在画面中的空间位置，例如 foreground_left, center, background_right"
    )

    action: str = Field(
        ...,
        description="当前镜头人物动作"
    )

    emotion: str = Field(
        ...,
        description="人物当前表情和情绪"
    )
    

class Segment(BaseModel):
    scene_name: str = Field(..., description="分镜所在场景名，与输入scene_library中scene_name对齐，多个分镜可以属于同一个场景")
    duration_budget: float = Field(..., ge=1.0, le=15.0, description="预估分镜总时长, 单位秒")
    shot_type: str = Field(..., description="用于指挥AI生成视频时镜头动作，例如：中景/远景/人像/平时/俯视/跟随人物等")
    prompt_for_video: str = Field(..., description="用于生成视频的提示词，例如：一位30岁的亚洲女性老板双手猛拍桌子、怒不可遏的特写镜头。坐在她对面的25岁男性程序员神情紧张。")
    target_emotion: str = Field(..., description="分镜整体情绪，例如：冲突/高潮/过渡等")
    audio_timeline: List[AudioTimeline] = Field(default=[], description="分镜下人物台词")
    role_view_info: list[SegmentRoleView] = Field(default=[], description="分镜下人物出境信息")

class StoryBoard(BaseModel):
    segments: List[Segment] = Field(..., description="分镜脚本列表，注意时间连续性")

STORYBOARD_SYSTEM_PROMPT = """
# Role
你是一位严谨的商业短视频分镜导演。你的任务是接棒创意总监的宏观设想，将其落地为高可执行性、能直接触发 AI 多角色配音和 AI 生视频的结构化分镜脚本。

# Task
阅读创意总监提供的【视频脚本】包括 角色列表 场景列表 核心卖点 和 剧情大纲(分段提供) 四个部分 ，生成一套全新的、用于 AI 多模态生产的结构化分镜脚本。

# Multi-Role & Technical Rules (视听对齐铁律)
1. 需要为新分镜划分 [宏观场景（scene_name）]，并设定 [预估总时长预算] (duration_budget)。
2. 音频解耦与多角色对齐 (音频 List 核心规则)：
   - 每个镜头的音频部分必须是一个列表 `audio_timeline`。
   - 必须明确指定说话的 `role_name`（如：女高管、程序员、旁白），必须使用用户提供的【角色列表】role_library中role_name。禁止使用模糊统称和编造新角色名。
   - 必须通过相对时间戳 `start_offset` 和 `end_offset` 标明每句话在当前镜头内的起止时间（例如：在这个5秒的镜头里，角色 A 从第 0 秒说到第 3 秒，角色 B 从第 3.2 秒说到第 5 秒）。
3. 台词时长严格按照【剧情大纲】中台词 predict_duration 计算
4. 画面描述可执行性：`prompt_for_video` 必须是纯名词/动词的高清场景、动作、景别描绘，以便直接输入给 flux2 生成，禁止出现“感到悲伤”、“技术很厉害”等 AI 无法直接作画的抽象形容词。
5. 人物一致性命名：在画面描述中出现主角时，必须使用统一的特征词（例如：一个25岁的年轻格子衫男程序员），严禁使用“他/她”或不同的称呼。
6. 分镜时长：15s以内，尽量拆分分镜以符合要求。

# 角色列表
```Json
{role_library}
```

# 场景列表
```Json
{scene_library}
```

# 核心卖点
```Json
{core_shell_point}
```
"""

STORYBOARD_QUERY_PROMPT = """
请根据以下【剧情大纲】，严格生成全新的分镜脚本。

1. 【剧情大纲】（来自创意总监的宏观设想）

```Json
{plot_script}
```

【输出格式要求】（必须严格遵守）：
- 输出一个 JSON 对象，顶层必须是 "segments" 字段，其值为分镜对象数组。
- 数组中每个分镜对象，字段名必须严格使用下列字段，一个不多一个不少：
  - "scene_name"：字符串，分镜所在场景名，与场景库中的 scene_name 对齐。
  - "duration_budget"：数字，分镜预估时长（秒），范围 1~15。
  - "shot_type"：字符串，镜头动作，例如 "中景推镜"、"人物特写"、"俯视全景"。
  - "prompt_for_video"：字符串，用于生成视频的画面描述，纯名词/动词，例如 "一位30岁的亚洲女性老板双手猛拍桌子，怒不可遏，面前坐着的25岁男程序员神情紧张"。
  - "target_emotion"：字符串，分镜整体情绪，例如 "冲突"、"高潮"、"过渡"。
  - "audio_timeline"：数组，分镜下人物台词。每项包含 "role_name"（角色名）、"lines"（台词）、"audio_style"（语气）、"lines_flag"（head/body/tail/all）、"start_offset"（秒）、"end_offset"（秒）。无台词则留空数组 []。
  - "role_view_info"：数组，分镜下人物出境信息。每项包含 "role_name"、"visibility"（visible/partial/invisible）、"position"、"action"、"emotion"。无人物则留空数组 []。

【示例】单个分镜对象：
```json
{{"scene_name": "办公室", "duration_budget": 3, "shot_type": "中景推镜", "prompt_for_video": "现代办公室内景，办公桌，电脑，员工背影", "target_emotion": "过渡", "audio_timeline": [], "role_view_info": []}}
```

【铁律】
- 禁止使用 ```json 代码块包裹整个输出，直接输出 JSON 本体。
- 禁止输出任何解释性文字、Markdown 或额外字段。
请生成分镜脚本：
"""

storyboard_model = model.with_structured_output(StoryBoard)


def strip_markdown_fence(text: str) -> str:
    """剥离 LLM 输出中的 Markdown 代码块围栏（```json ... ```）。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n", 1)
        if len(lines) > 1:
            text = lines[1]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


async def ainvoke_storyboard_robust(messages, config=None) -> StoryBoard:
    """调用分镜生成模型并容错解析。

    部分模型（如 deepseek-v4-flash）对 json_schema 遵循不稳定，可能返回
    Markdown 围栏包裹或字段名漂移的 JSON。此函数先尝试结构化输出，失败时
    退回到原始文本解析：剥离围栏、兼容 {segments: [...]} 或纯数组两种结构。
    """
    try:
        return await storyboard_model.ainvoke(messages, config=config)
    except Exception as e:
        logger.warning(f'storyboard structured output failed, fallback to manual parse: {str(e)[:200]}')
        raw = await model.ainvoke(messages, config=config)
        content = raw.content if isinstance(raw.content, str) else str(raw.content)
        cleaned = strip_markdown_fence(content)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # 模型可能输出 `` ```json {...} ``` `` 且带多余尾注，尝试再剥一次
            cleaned = strip_markdown_fence(strip_markdown_fence(cleaned))
            data = json.loads(cleaned)
        if isinstance(data, dict) and "segments" in data:
            return StoryBoard.model_validate(data)
        if isinstance(data, dict) and "storyboard" in data:
            return StoryBoard(segments=data["storyboard"])
        if isinstance(data, list):
            return StoryBoard(segments=data)
        raise ValueError(f"无法解析的分镜输出: {cleaned[:200]}")


#节点C##########################################################################################################

class CharacterAsset(BaseModel):
    role_name: str = Field(..., description="角色名，与输入【角色清单】中 role_name 对齐。严禁编造角色名")

    visual_anchor_prompt: Optional[str] = Field(
        default=None,
        description="用于控制模型生成一致性长相的中文定妆照提示词。必须是单人、正脸、干净背景的半生或者全身照。如果不出镜，则不填。请用一段连贯、电影级的自然语言描述（不要用逗号标签堆砌），按这个顺序组织：角色主体（性别、年龄、发型、发色、五官特征）→ 服装与配饰（款式、颜色、材质、细节）→ 姿态与表情 → 光线与摄影（布光方向、质感、景深、焦段）→ 背景与环境氛围。重要：本提示词仅用于生成人物参考图（供后续生视频保持角色一致），因此**严禁让角色手持任何推广产品或商品**（如泡面、酸奶、手机等），双手应自然摆放或做自然姿态，不要描写手中持有物品。例如：" \
        "电影级人物定妆照，一位二十四五岁的亚洲年轻女性正对镜头，五官清秀，柳叶眉，杏眼含笑意，鼻梁挺直，唇色自然。墨色长发自然垂落，发尾微卷，刘海轻覆额头。她身穿一件奶白色针织开衫，内搭同色系高领内搭，领口点缀一条细银链，锁骨处一枚小月亮吊坠，下身是浅驼色直筒裤。她双手自然交叠于身前，嘴角微扬，神情温柔从容。柔和漫射的窗光从侧面打来，为发丝勾勒出细腻光边，皮肤呈现通透质感，背景虚化成一团温暖的米色光晕，浅景深，85mm 镜头，氛围安静治愈。"
    )


class CharacterManifest(BaseModel):
    character_list: list[CharacterAsset] = Field(..., description="角色资产信息")


PRODUCER_SYSTEM_PROMPT = """
# Role

你是一位技术型电影制片人，同时是精通 AI 图像生成的提示词工程师。你专门负责从剧本中提取出具体需要采购和制作的”资产清单”（Asset Manifest），并为每个出镜角色撰写可用于 AI 绘图的、电影级的”定妆照提示词”。

# Task

阅读用户提供的描述信息，提取出本片中所有需要出镜的实体角色，并为每个角色写一段高质量、写实、电影级的中文定妆照提示词（visual_anchor_prompt），用于控制 AI 生成该角色的一致长相。

# Rules

- 提取完整性：必须遍历所有分镜和角色清单，找出所有出镜的角色，不出镜角色不需要提取。
- 一致性优先：提示词必须能让 AI 在后续多个分镜中稳定复现同一张脸，因此要写清五官、发型、年龄、体型等可复现的锚点特征。

# 定妆照提示词写作规范（visual_anchor_prompt）

必须用一段连贯、写实的自然语言描述，**不要用逗号分隔的标签堆砌，也不要写成键值对清单**。按以下顺序展开成一个完整的段落：

1. 主体开场：一句点明角色（性别、年龄段、职业/身份感）、正对镜头、单人构图。
2. 面部锚点：五官形状（眉、眼、鼻、唇）、肤色、脸型、发型与发色——这是保证跨分镜长相一致的核心，务必具体。
3. 服装与配饰：款式、颜色、材质、标志性配饰（首饰、领口、腰带等），细节要可被视觉化。
4. 姿态与表情：自然放松的姿态，明确的神情（温和、锐利、疲惫等）。**双手不要持有任何物品**——严禁让角色手持推广产品或商品（如泡面、酸奶、手机、礼盒等），双手自然摆放或做自然姿态即可。
5. 光线与摄影：布光方向与质感（柔和窗光、硬朗顶光、金色逆光等）、皮肤质感、景深、焦段、氛围词。
6. 背景：干净、不喧宾夺主，起到烘托人物的作用即可。

语言要求：写实、具体、有画面感，避免抽象或主观的修饰（如"很美""气质好"），代之以可被模型量化的视觉特征（如"长发及腰""肤色冷白""眼神专注"）。全程使用中文，风格统一、克制、专业。
"""

PRODUCER_QUERY_PROMPT = """
请根据以下输入的 【角色清单】、【全局画风母版】和【分镜脚本】，提炼角色资产清单：

1. 角色清单（来自创意总监的输出）
```Json
{role_library}
```

2. 全局画风母版
```Json
{style_template}
```

3. 分镜脚本
```Json
{storyboard}
```

{retry_messages}
【输出格式要求】（必须严格遵守）：
- 输出一个 JSON 对象，顶层必须是 "character_list" 字段，其值为角色对象数组。
- 数组中每个角色对象，字段名必须严格为以下两个：
  - "role_name"：字符串，角色名，必须与【角色清单】中的 role_name 完全一致，严禁编造。
  - "visual_anchor_prompt"：字符串或 null。该角色出镜时填写一段中文电影级定妆照提示词（单人、正脸、干净背景，用于 AI 生成一致性长相）；**严禁让角色手持任何推广产品或商品（如泡面、酸奶、手机等），双手自然摆放**；不出镜则为 null。
- 禁止使用 ```json 代码块包裹整个输出，直接输出 JSON 本体。
- 禁止输出任何解释性文字、Markdown 标题或额外字段。
请输出角色资产信息：
"""

producer_model = model.with_structured_output(CharacterManifest)


async def ainvoke_producer_robust(messages, config=None) -> CharacterManifest:
    """调用角色资产模型并容错解析。

    与 ainvoke_storyboard_robust 同理：部分模型对 json_schema 遵循不稳定，
    可能返回 Markdown 围栏/标题包裹的内容。失败时退回原始文本解析。
    """
    try:
        return await producer_model.ainvoke(messages, config=config)
    except Exception as e:
        logger.warning(f'producer structured output failed, fallback to manual parse: {str(e)[:200]}')
        raw = await model.ainvoke(messages, config=config)
        content = raw.content if isinstance(raw.content, str) else str(raw.content)
        cleaned = strip_markdown_fence(content)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            cleaned = strip_markdown_fence(strip_markdown_fence(cleaned))
            data = json.loads(cleaned)
        if isinstance(data, dict) and "character_list" in data:
            return CharacterManifest.model_validate(data)
        if isinstance(data, dict) and "characters" in data:
            return CharacterManifest(character_list=data["characters"])
        if isinstance(data, dict) and "roles" in data:
            return CharacterManifest(character_list=data["roles"])
        raise ValueError(f"无法解析的角色资产输出: {cleaned[:200]}")


def _extract_json_dict(content: str) -> dict | list:
    """剥离 Markdown 围栏/标题并解析为 JSON。"""
    cleaned = strip_markdown_fence(content)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        cleaned = strip_markdown_fence(strip_markdown_fence(cleaned))
        return json.loads(cleaned)


async def ainvoke_structured_robust(
    structured_model,
    schema,
    messages,
    config=None,
    *,
    array_key: str | None = None,
    alias_map: dict | None = None,
    name: str = "output",
):
    """通用结构化输出容错调用。

    deepseek-v4-flash 等模型对 json_schema 遵循不稳定，可能返回 Markdown 围栏/
    标题包裹或字段漂移的 JSON。先尝试 with_structured_output 快路径，失败时
    退回原始文本解析（剥围栏 + 兼容字段别名）。

    Args:
        structured_model: with_structured_output 包装后的模型。
        schema: Pydantic 模型类，用于校验。
        messages: 输入消息。
        config: 调用配置。
        array_key: 若模型可能返回纯数组而非 {key: [...]}，此参数指定 key。
        alias_map: 模型漂移字段到 schema 字段的映射，例如 {"voice_type": "selected_voice_type"}。
        name: 错误信息中的描述名。
    """
    try:
        return await structured_model.ainvoke(messages, config=config)
    except Exception as e:
        logger.warning(f'{name} structured output failed, fallback to manual parse: {str(e)[:200]}')
        raw = await model.ainvoke(messages, config=config)
        content = raw.content if isinstance(raw.content, str) else str(raw.content)
        try:
            data = _extract_json_dict(content)
        except Exception as parse_err:
            from pydantic import ValidationError
            raise ValidationError.from_exception_data(
                schema.__name__, [{"type": "json_invalid", "loc": ("root",), "input": content[:200], "ctx": {"error": str(parse_err)}}]
            )

        if isinstance(data, list):
            if array_key:
                return schema(**{array_key: data})
            from pydantic import ValidationError
            raise ValidationError.from_exception_data(
                schema.__name__, [{"type": "json_invalid", "loc": ("root",), "input": content[:200], "ctx": {"error": "expected object, got array"}}]
            )

        if not isinstance(data, dict):
            from pydantic import ValidationError
            raise ValidationError.from_exception_data(
                schema.__name__, [{"type": "json_invalid", "loc": ("root",), "input": content[:200], "ctx": {"error": "expected object"}}]
            )

        if alias_map:
            for drift_key, real_key in alias_map.items():
                if drift_key in data and real_key not in data:
                    data[real_key] = data.pop(drift_key)

        try:
            return schema.model_validate(data)
        except Exception as e:
            from pydantic import ValidationError
            if isinstance(e, ValidationError):
                raise
            raise ValidationError.from_exception_data(
                schema.__name__, [{"type": "value_error", "loc": ("root",), "input": content[:200], "ctx": {"error": str(e)}}]
            )


#选择音色 ##########################################################################################################

class SelectVoiceID(BaseModel):
    selected_voice_type: str = Field(
        ...,
        description='选中【候选音色列表】中键值对的 key'
    )
    reason: str = Field(description='一句话选择理由')

VOICE_SELECT_PROMPT = """
# Role
你是一位资深的配音导演。

# Task
请从以下【候选音色列表】中，挑选出最符合【剧本人物描述】的一款音色。

【剧本人物描述】：
{target_desc}

【候选音色列表】：
{voice_dict}


# Rules
【评审要求】：
1. 深入理解文本的意境、语气、语速和适用场景（例如：家居数码宣传需要商务/科技感与亲和力兼顾）。
2. 必须且只能从列表中选择一个最完美的 `key`。
3. 上次错误经验（可能为空）：
{error_msg}

# Output Format
请严格按照规定的 JSON 格式输出，包含以下两个字段：

selected_voice_type: 选中音色在候选列表中的 key（例如 "ICL_ur...aojiaogongzi_tob"）

reason: 选择该音色的一句话理由

【严重警告】：
绝对不要输出任何 Markdown 标记（不要使用 json 或 ），仅输出纯 JSON 字符串！
"""


voice_model = model.with_structured_output(SelectVoiceID)

#修改对话，防超时 ##########################################################################################################

class ReduceLines(BaseModel):
    actor_lines: List[ActorLines] = Field(
        ...,
        description="本段剧情的台词信息"
    )


REDUCE_LINES_PROMPT = """
你是一位严谨的商业短视频分镜导演。简化【原台词】，使台词总时长符合【预期时长】。
同步修改台词（lines）和 每句话预估时长（predict_duration）

【原台词】
{ori_lines}

【原时长】
{ori_duration:.2f}秒

【预期时长】
{targe_duration:.2f}秒

禁止：
- 修改role_name
"""

reduce_lines_model = model.with_structured_output(ReduceLines)

#修改对话，防超时 ##########################################################################################################
class LinesInfo(BaseModel):
    role_name: str = Field(..., description="角色名，与输入要保持一致")
    text: str = Field(..., description='修改后台词')

class ReloadLines(BaseModel):
    actor_lines: list[LinesInfo] = Field(description='修改后的台词列表')

ReloadLinesPrompt = """
当前场景目标时长：
{plot_target_duration:.2f}秒

当前TTS总时长：
{plot_voice_duration:.2f}秒

需要压缩比例：
{compress_ratio:.2f}

请保持剧情不变，台词条数和人物不变。

按比例压缩每个角色台词。

原场景：

{scene_text}

只能修改 text。

禁止：

- 删除 role_name
- 修改 role_name
- 新增 role_name
"""

reload_lines_model = model.with_structured_output(ReloadLines)


#生成场景 ##########################################################################################################
class ScenePrompt(BaseModel):
    scene_name: str = Field(
        ...,
        description='提示词对应场景名，与输入【场景清单】中scene_name字段对齐，严禁编造场景名。'
    )
    scene_prompt: str = Field(
        ..., 
        description='使用flux2 klien生成场景图片的提示词。中文 prompt。不要解释。不要添加标题。')

class SceneManifest(BaseModel):
    scene_prompt_list: list[ScenePrompt] = Field(description='场景提示词列表，每个场景对应一个元素。')
    
SCENE_GENERATE_PROMPT = """
你是一名专业电影美术指导和 AI 图像提示词工程师。

你的任务：
根据【场景清单】、【整体视觉风格】，为每个场景生成一段适用于 Krea2 文生图模型的、电影级写实的【场景参考图（Scene Asset）】提示词。

目标：
生成高质量、电影级、写实的场景提示词，供多个视频分镜共享作为场景资产。因此必须稳定、通用、可复现，且**不含任何人物**。

输入：

【场景清单】
{scene_description}

【整体视觉风格】
{visual_style}

【上次报错信息】（可能为空）
{error_message}

【输出格式要求】（必须严格遵守，输出 JSON）：
- 输出一个 JSON 对象，顶层必须是 "scene_prompt_list" 字段，其值为场景提示词对象数组。
- 数组中每个场景对象，字段名必须严格为以下两个：
  - "scene_name"：字符串，场景名，必须与【场景清单】中的 scene_name 字段完全一致，严禁编造。
  - "scene_prompt"：字符串，该场景的电影级写实提示词（见下方写作规范）。
- 禁止使用 ```json 代码块包裹整个输出，直接输出 JSON 本体。
- 禁止输出任何解释性文字、Markdown 标题或额外字段。

【scene_prompt 写作规范】：
1. 只描述环境与空间，严禁出现任何人物。禁止使用以下词汇：people、person、man、woman、character、human、girl、boy、crowd、portrait。
2. 写一段连贯、写实的自然语言描述（不要用逗号标签堆砌，不要用键值对清单），按以下顺序展开：
   - 空间与主体：点明场景类型（办公室、街道、房间、森林等）与核心主体结构；
   - 空间细节：建筑结构、家具、物品、材质（木、石、玻璃、织物等），按空间从近到远交代层次；
   - 色彩与光影：整体色调、光源方向与质感（暖色顶灯、冷调窗光、金色逆光、霓虹等）、明暗对比；
   - 氛围：通过空气感（雾气、尘粒、光晕）、天气、时间感来传递情绪基调；
   - 摄影参数：镜头焦段、景深、构图、拍摄视角，让画面有电影摄影质感。
3. 保持场景资产的中立性：画面中不要隐含叙事或人物活动的强暗示，让任何分镜都能套用。
4. 语言风格：写实、具体、有画面感，避免抽象形容（如"氛围很好"），代之以可视觉化的特征（如"低角度广角"、"通透的漫射光"、"深褐木质地板"）。使用中文。
"""

scene_generate_model = model.with_structured_output(SceneManifest)

#生成分镜帧提示词 ##########################################################################################################


GENEERATE_SEGMENT_FRAME ="""
生成一张电影级分镜首帧图片。

参考信息：
- 人物参考图用于保持人物身份，包括脸部特征、发型、年龄、体型、服装风格，可能存在多个角色，json格式。
- 场景参考图用于保持环境结构、空间布局、建筑风格和整体光影氛围。

要求生成一个完整的新画面，让人物自然存在于场景环境中。

【人物】
{角色名称}
外貌：
{角色描述}

动作：
{人物当前动作}

表情：
{人物情绪}

人物必须保持与参考图片一致的身份特征，不改变脸型、五官、发型和服装特点。

【场景】
{场景描述}

场景需要保持参考图片中的环境特点，同时根据剧情需要进行合理扩展。

【镜头】
景别：
{远景 / 中景 / 近景 / 特写}

视角：
{平视 / 俯视 / 仰视 / 侧面}

构图：
{人物位置、空间关系}

【光影】
{时间、天气、光照描述}

【画面风格】
电影摄影风格，真实自然，高细节，真实光影，影视剧截图质感。
"""

from typing import List, Literal, Optional

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from app.config import settings

model = init_chat_model(
    settings.LLM_NAME,
    temperature = 0.7,
    model_provider='openai',
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY,
    configurable_fields=("temperature")
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
        description="全局通用的生图后缀。例如：'cinematic lighting, photorealistic, 4k resolution, shot on RED camera'。"
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
    predict_duration: float = Field(..., ge=0.5, description='台词预估时长，单位秒。每段剧情中所有台词的predict_duration之和要小于等于 end_time-start_time')
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

class CloneAnalysis(BaseModel):
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
    plot_script: List[ClonePlotScript] = Field(
        ...,
        description="新视频的剧情大纲"
    )
    

CREATIVE_SYSTEM_PROMPT = """
# Role

你是一位精通微短剧和信息流广告（Feeds AI）的资深多模态创意总监。你擅长逆向拆解爆款视频的“骨架底层逻辑”，并将其完美重组到全新的商业主题中。

# Task

分析用户提供的【原视频分析文本】【原视频剧情大纲】与【全新主题梗概】，在保持原视频“黄金3秒、核心冲突、情绪节奏、痛点切入点”完全一致的前提下，进行宏观创意换血。

# Rules & Constraints

- 创意对齐：新大纲的每一个情节转折，必须严格对应原视频的节奏骨架。
- 严禁具体分镜：此阶段严禁输出“镜头 1、镜头 2”等详细分镜表格，只做宏观剧情和创意设定的输出。
- 每段剧情中台词的预估时长（predict_duration）之和要小于等于当前剧情的end_time-start_time。
"""

CREATIVE_QUERY_PROMPT = """
请根据以下输入，执行创意换血任务：

1. 原视频分析文本
```Markdown
{analysis_focus}
```

2. 原视频剧情大纲
```Json
{plot_script}
```

3. 全新主题/产品梗概（Clone Theme）
```Text
{clone_theme}
```

4. 上次失败经验（可能为空）：
```Text
{error_message}
```

请开始你的创意创作：
"""

# RESET_LINES_PROMPT = """
# 请检查上述输出结构中 plot_script 每个元素。
# 确保 actor_lines
# """

creative_model = model.with_structured_output(CloneAnalysis)
creative_model_strict = model.with_structured_output(CloneAnalysis, strict=True)


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

class Segment(BaseModel):
    scene_name: str = Field(..., description="分镜所在场景名，与输入scene_library中scene_name对齐，多个分镜可以属于同一个场景")
    duration_budget: float = Field(..., ge=0.0, le=5.0, description="预估分镜总时长, 单位秒")
    shot_type: str = Field(..., description="用于指挥AI生成视频时镜头动作，例如：中景/远景/人像/平时/俯视/跟随人物等")
    prompt_for_video: str = Field(..., description="用于生成视频的提示词，例如：一位30岁的亚洲女性老板双手猛拍桌子、怒不可遏的特写镜头。坐在她对面的25岁男性程序员神情紧张。")
    target_emotion: str = Field(..., description="分镜整体情绪，例如：冲突/高潮/过渡等")
    audio_timeline: List[AudioTimeline] = Field(default=[], description="分镜下人物台词")

class StoryBoard(BaseModel):
    segments: List[Segment] = Field(..., description="分镜脚本列表，注意时间连续性")

STORYBOARD_SYSTEM_PROMPT = """
# Role
你是一位严谨的商业短视频分镜导演。你的任务是接棒创意总监的宏观设想，将其落地为高可执行性、能直接触发 AI 多角色配音和 AI 生视频的结构化分镜脚本。

# Task
阅读创意总监提供的【视频脚本】包括 人物(role_library) 场景(scene_library,global_style) 推广点(core_shell_point) 和剧情大纲(slot_script) 四个部分 ，生成一套全新的、用于 AI 多模态生产的结构化分镜脚本。

# Multi-Role & Technical Rules (视听对齐铁律)
1. 需要为新分镜划分 [宏观场景（scene_name）]，并设定 [预估总时长预算] (duration_budget)。
2. 音频解耦与多角色对齐 (音频 List 核心规则)：
   - 每个镜头的音频部分必须是一个列表 `audio_timeline`。
   - 必须明确指定说话的 `role_name`（如：女高管、程序员、旁白），必须使用用户提供的【视频脚本】role_library中role_name。禁止使用模糊统称和编造新角色名。
   - 必须通过相对时间戳 `start_offset` 和 `end_offset` 标明每句话在当前镜头内的起止时间（例如：在这个5秒的镜头里，角色 A 从第 0 秒说到第 3 秒，角色 B 从第 3.2 秒说到第 5 秒）。
3. 台词时长严格按照【视频脚本】中台词 predict_duration 计算
4. 画面描述可执行性：`prompt_for_video` 必须是纯名词/动词的高清场景、动作、景别描绘，以便直接输入给 Midjourney 或 Runway 生成，禁止出现“感到悲伤”、“技术很厉害”等 AI 无法直接作画的抽象形容词。
5. 人物一致性命名：在画面描述中出现主角时，必须使用统一的特征词（例如：一个25岁的年轻格子衫男程序员），严禁使用“他/她”或不同的称呼。
6. 分镜时长：15s以内，尽量拆分分镜以符合要求。
"""

STORYBOARD_QUERY_PROMPT = """
请根据以下输入，严格生成全新的分镜 JSON 数组：

1. 视频脚本（来自创意总监的宏观设想）

```Json
{plot_script}
```
{notice}
请生成分镜脚本：
"""

storyboard_model = model.with_structured_output(StoryBoard)


#节点C##########################################################################################################

class CharacterAsset(BaseModel):
    role_name: str = Field(..., description="角色名，与输入【角色清单】中 role_name 对齐。严禁编造角色名")

    visual_anchor_prompt: Optional[str] = Field(
        default=None,
        description="用于控制模型生成一致性长相的英文定妆照提示词。必须是单人、正脸、干净背景的高清半身肖像描述。如果不出镜，则不填。例如：" \
        "Photorealistic, ultra-detailed close-up portrait of a woman with long wavy brown hair tied neatly back, wearing rimless clear-lensed glasses with a sophisticated silver rim. She has a subtle blue rose hair clip in her hair with a small navy ribbon, and a delicate silver necklace with a heart-shaped turquoise pendant. The background is pure white, and the soft, warm professional lighting creates a focused and professional atmosphere. The composition is a standard head-and-shoulders ID photo style, with a shallow depth of field. Emphasis is placed on the neat hair texture, reflective glass surfaces, healthy skin tone, and the delicate jewelry details. The overall style is business-oriented and professional, with a confident and focused mood."
    )

class CharacterManifest(BaseModel):
    character_list: list[CharacterAsset] = Field(..., description="角色资产信息")


PRODUCER_SYSTEM_PROMPT = """
# Role

你是一位技术型电影制片人，专门负责从剧本中提取出具体需要采购和制作的“资产清单”（Asset Manifest）。

# Task

阅读用户提供的描述信息，提取出本片中所有需要出镜的实体角色，并为他们定制用于 AI 绘图的“定妆照提示词”。

# Rules

- 提取完整性：必须遍历所有分镜和角色清单，找出所有出镜的角色，不出镜角色不需要提取。
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
请输出角色资产信息：
"""

producer_model = model.with_structured_output(CharacterManifest)


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
```Text
{target_desc}
```

【候选音色列表】：
```Json
{voice_dict}
```

# Rules
【评审要求】：
1. 深入理解文本的意境、语气、语速和适用场景（例如：家居数码宣传需要商务/科技感与亲和力兼顾）。
2. 必须且只能从列表中选择一个最完美的 `key`。
3. 上次错误经验（可能为空）：
{error_msg}
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

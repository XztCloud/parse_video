from typing import List, Optional

from langchain.chat_models import init_chat_model
from pydantic import BaseModel, Field
from app.config import settings

model = init_chat_model(
    settings.LLM_NAME,
    temperature = 0.7,
    model_provider='openai',
    base_url=settings.LLM_BASE_URL,
    api_key=settings.LLM_API_KEY
)

class CharacterInfo(BaseModel):
    role_name: str = Field(description="角色在剧本中的唯一名称。例如：'女高管'、'男程序员'、'旁白'。")
    gender: str = Field(description="角色的性别。取值范围通常为：'男'、'女'、'未知/通用'（如纯配音旁白）。")
    age: int = Field(description="角色的具体年龄或大致年龄段（如 25），用于控制 TTS 的声音成熟度和生图的年龄感。")
    voice_style_guide: str = Field(
        description="大模型对该角色声音风格的建议描述。例如：'声音低沉、带有磁性、语速中等'。"
    )
    effect: str = Field(
        description="该角色在剧本中的作用"
    )
    visual_anchor_prompt: str = Field(
        description="用于控制 Midjourney/Flux 生成一致性长相的英文定妆照提示词。必须是单人、正脸、干净背景的高清肖像描述。如果是旁白，则填 None。"
    )
    summary: str = Field(
        description="使用中文概括人物，例如：'仅在实景环节出镜，为戴眼镜的办公场景程序员，用于展示产品实际使用场景'"
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
    role_name: str = Field(description="角色在剧本中的唯一名称。一定要使用已经创建的角色，且角色名要一致")
    lines: str = Field(description="角色台词")

class CloneSlotScript(BaseModel):
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
    slot_script: List[CloneSlotScript] = Field(
        ...,
        description="新视频的剧情大纲"
    )



# class CreateOutput(BaseModel):
#     analysis_focus: CloneAnalysisFocus
    

creative_system_prompt = """
# Role

你是一位精通微短剧和信息流广告（Feeds AI）的资深多模态创意总监。你擅长逆向拆解爆款视频的“骨架底层逻辑”，并将其完美重组到全新的商业主题中。

# Task

分析用户提供的【原视频分析文本】【原视频剧情大纲】与【全新主题梗概】，在保持原视频“黄金3秒、核心冲突、情绪节奏、痛点切入点”完全一致的前提下，进行宏观创意换血。

# Rules & Constraints

- 创意对齐：新大纲的每一个情节转折，必须严格对应原视频的节奏骨架。
- 严禁具体分镜：此阶段严禁输出“镜头 1、镜头 2”等详细分镜表格，只做宏观剧情和创意设定的输出。
"""

creative_model = model.with_structured_output(CloneAnalysis)

# creative_slot_model = model
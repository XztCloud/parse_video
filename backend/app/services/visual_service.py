import base64
import os
from pathlib import Path
from typing import Optional
from ..config import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


# ---------------------------------------------------------------------------
#  图像工具函数
# ---------------------------------------------------------------------------

def encode_image_to_base64(image_path: str) -> str:
    """将图片文件编码为 base64 字符串。"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def get_image_media_type(image_path: str) -> str:
    """根据文件扩展名推断 MIME 类型。"""
    ext = Path(image_path).suffix.lower()
    media_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }
    return media_map.get(ext, "image/jpeg")


def build_image_content(image_path: str) -> dict:
    """构建 LangChain 多模态消息所需的 image_url 内容块。"""
    b64 = encode_image_to_base64(image_path)
    media_type = get_image_media_type(image_path)
    return {
        "type": "image_url",
        "image_url": {"url": f"data:{media_type};base64,{b64}"},
    }


# ---------------------------------------------------------------------------
#  VideoFrameSummarizer 核心类
# ---------------------------------------------------------------------------

class VideoFrameSummarizer:
    """
    视频帧画面总结器。

    每次调用 summarize_frames() 传入四帧图像，LLM 会：
      1. 观察当前四帧的画面内容
      2. 参考之前已总结的帧画面描述（如有）
      3. 输出一段连贯的、与上下文衔接的画面总结

    典型用法：
        summarizer = VideoFrameSummarizer()
        summary_1 = summarizer.summarize_frames(["f0.jpg", "f1.jpg", "f2.jpg", "f3.jpg"])
        summary_2 = summarizer.summarize_frames(["f4.jpg", "f5.jpg", "f6.jpg", "f7.jpg"])
        # summary_2 会自动参考 summary_1 的内容，保持描述连贯
    """

    # 系统提示词
    SYSTEM_PROMPT = (
        "你是一个专业的视频画面描述助手。你的任务是观察给定的视频帧图像，"
        "并用简洁、准确、连贯的语言描述画面中发生的事情。\n\n"
        "规则：\n"
        "1. 描述要涵盖场景、人物动作、物体变化等关键信息。\n"
        "2. 如果存在「之前的画面总结」，你必须参考它，使新的描述与之前的叙述自然衔接，"
        "   避免重复已有信息，重点描述新出现或发生变化的内容。\n"
        "3. 如果画面之间有明显的动作连续性，请体现出来。\n"
        "4. 输出一段完整的中文描述，不要使用列表或分点格式。"
    )

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: int = 1024,
    ):
        """
        初始化总结器。

        Args:
            model_name: 模型名称，需支持多模态（视觉）输入。
            base_url:  自定义 API 端点（兼容 OpenAI 接口的服务）。
            api_key:   API 密钥，默认从环境变量 OPENAI_API_KEY 读取。
            temperature: 生成温度。
            max_tokens:  最大输出 token 数。
        """
        llm_kwargs = {
            "model": model_name,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if api_key:
            llm_kwargs["api_key"] = api_key
        if base_url:
            llm_kwargs["base_url"] = base_url

        self.llm = ChatOpenAI(**llm_kwargs)
        # 保存所有历史总结，用于上下文串联
        self.summary_history: list[str] = []

    # -----------------------------------------------------------------------
    #  公开接口
    # -----------------------------------------------------------------------

    def summarize_frames(self, frame_paths: list[str]) -> str:
        """
        对四帧视频帧进行画面总结，自动关联之前的总结历史。

        Args:
            frame_paths: 四帧图片的文件路径列表，按时间顺序排列。

        Returns:
            当前四帧的画面总结文本。
        """
        # if len(frame_paths) != 4:
        #     raise ValueError(f"需要恰好 4 帧图像，当前传入了 {len(frame_paths)} 帧。")

        # 1. 构建消息列表
        messages = self._build_messages(frame_paths)

        # 2. 调用 LLM
        response = self.llm.invoke(messages)
        summary = response.content.strip()

        # 3. 记录到历史
        self.summary_history.append(summary)

        return summary

    def get_full_history(self) -> str:
        """返回所有历史总结的拼接文本。"""
        return "\n\n".join(
            f"【第 {i + 1} 组帧总结】{s}"
            for i, s in enumerate(self.summary_history)
        )

    def clear_history(self) -> None:
        """清空历史总结记录。"""
        self.summary_history.clear()

    # -----------------------------------------------------------------------
    #  内部方法
    # -----------------------------------------------------------------------

    def _build_messages(self, frame_paths: list[str]) -> list:
        """构建发送给 LLM 的完整消息列表。"""
        messages = [SystemMessage(content=self.SYSTEM_PROMPT)]

        # --- 用户消息：文本 + 图像 ---
        user_parts: list[dict] = []

        # 如果有历史总结，先告诉 LLM 之前的上下文
        if self.summary_history:
            context_text = (
                "以下是之前已经总结的帧画面：\n"
                + self.get_full_history()
                + "\n\n请参考以上内容，结合下面新的四帧图像进行连贯描述："
            )
            user_parts.append({"type": "text", "text": context_text})
        else:
            user_parts.append({
                "type": "text",
                "text": "请观察以下四帧视频图像，描述画面内容：",
            })

        # 依次添加四帧图像
        for idx, path in enumerate(frame_paths):
            if not os.path.exists(path):
                raise FileNotFoundError(f"图像文件不存在: {path}")
            user_parts.append({
                "type": "text",
                "text": f"\n--- 第 {idx + 1} 帧 ---",
            })
            user_parts.append(build_image_content(path))

        messages.append(HumanMessage(content=user_parts))
        return messages


class VisualService:
    @staticmethod
    async def analyze_frames(frame_paths: list[str], fps: float = 1.0) -> list[dict]:

        # ===== 运行 =====
        summarizer = VideoFrameSummarizer(
            model_name="doubao-seed-2.0-pro",
            base_url="https://ark.cn-beijing.volces.com/api/coding/v3",
            api_key="ebd2645e-7e6a-4235-bdf0-7ab08befc4b1",
        )
        print('1')
        segments = []
        batch_size = 4
        for i in range(0, len(frame_paths), batch_size):
            batch = frame_paths[i:i + batch_size]
            messages = [{"role": "user", "content": [{"text": "请分析以下视频帧，描述镜头画面内容，包括景别、画面主体、动作、场景环境。用简洁一句话描述。"}]}]
            try:
                summary_item = summarizer.summarize_frames(batch)
            except Exception as e:
                print(f'error is {e}')
                return None
            
            description = summary_item

            segments.append({"start_time": i * 1000 / fps, "end_time": min(i + batch_size, len(frame_paths)) * 1000 / fps, "shot_description": description})


            # for frame_path in batch:
            #     with open(frame_path, "rb") as f:
            #         img_b64 = base64.b64encode(f.read()).decode("utf-8")
            #     messages[0]["content"].append({"image": f"data:image/jpeg;base64,{img_b64}"})
            # response = MultiModalConversation.call(model="qwen-vl-plus", messages=messages)
            # description = ""
            # if response.status_code == 200:
            #     description = response.output.choices[0].message.content[0]["text"]
            # segments.append({"start_time": i / fps, "end_time": min(i + batch_size, len(frame_paths)) / fps, "shot_description": description})
        print(f'visual service:segments')
        return segments
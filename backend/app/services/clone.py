
from pathlib import Path

from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
import operator
from typing import Annotated, Literal, TypedDict

from langgraph.types import Command
from langgraph.graph import END, START, StateGraph
import pandas as pd
from pydantic import BaseModel
from app.models.video import CloneStatus

from app.database import SessionLocal
from app.models.script import CloneScript, Script
from app.models.video import Video
from app.services.llm import CloneAnalysis
from app.util import make_dir
from app.config import settings


class VideScript(TypedDict):
    analysis_focus: str     # 分析重点
    plot_script: str        # 剧情脚本
    storyboard: list[dict] | None  # 分镜信息列表
    width: int
    height: int
    duration: float
    

class CloneState(TypedDict):
    creative_messages: Annotated[list[AnyMessage], operator.add] # 仅用于保存创意llm对话，因为会跨节点
    video_url: str | None         # 复刻视频的URL
    clone_theme: str              # 主题
    guide: str | None             # 指导语
    ori_parameters: VideScript    # 原视频分析得到的参数
    clone_parameters: VideScript  # 复刻后的视频参数
    video_id: int   # 视频信息id
    clone_script_id: int # 复刻脚本id
    error: str



    

async def get_ori_context(state: CloneState):
    db = SessionLocal()
    try:
        script = db.query(Script).filter(Script.video_id == state['video_id']).first()
        video = db.query(Video).filter(Video.id == state['video_id']).first()
        if not script or not video:
            return Command(
                # state update
                update={'error': '原始脚本不存在，请先解析再复刻'},
                # control flow
                goto="process_error"
            )
        clone_script = CloneScript(
            script_id=script.id,
            clone_theme=state['clone_theme']
        )
        video.clone_progress = 10
        video.clone_status = CloneStatus.CLONING
        db.add(clone_script)
        db.commit()
        db.refresh(clone_script)
        ori_parameters = VideScript(
            analysis_focus=script.parse_pointer,
            plot_script=script.parse_script,
            storyboard=None,
            width=540,
            height=720,
            duration=32.0
        )
        return {
            "ori_parameters": ori_parameters,
            "clone_script_id": clone_script.id
        }
        
    except Exception as e:
        print(f'get_ori_context failed. {e}')
        message = f'获取原始脚本节点发生错误 {e}'
        return Command(
            # state update
            update={'error': message},
            # control flow
            goto="process_error"
        )
    finally:
        db.close()


async def convert_clone_to_md(response: CloneAnalysis, dir_path: str, clone_script_id: int) -> str:
    markdown_data = "# 视频脚本\n\n"
    markdown_data += "## 剧情人物\n\n"

    reset_title_list = []
    for role in response.role_library:
        item = {}
        item['名称'] = role.role_name
        item['性别'] = role.gender
        item['年龄'] = role.age
        item['声音'] = role.voice_style_guide
        item['剧情作用'] = role.effect
        reset_title_list.append(item)

    df = pd.DataFrame(reset_title_list)
    markdown_role_table = df.to_markdown(index=False)
    markdown_data += markdown_role_table
    markdown_data += "\n\n"

    markdown_data += "## 核心场景\n\n"
    reset_title_list = []
    for scene in response.scene_library:
        item = {}
        item['场景名'] = scene.scene_name
        item['描述'] = scene.environment_description
        item['调色风格'] = scene.color_grading
        reset_title_list.append(item)

    df = pd.DataFrame(reset_title_list)
    markdown_scene_table = df.to_markdown(index=False)
    markdown_data += markdown_scene_table
    markdown_data += "\n\n"

    markdown_data += "## 核心推广点\n\n"
    markdown_data += "### 1. 针对痛点\n\n"
    markdown_data += f"{response.core_shell_point.user_pain_point}\n\n"
    markdown_data += "### 2. 吸引点\n\n"
    markdown_data += f"{response.core_shell_point.hook_trigger}\n\n"
    markdown_data += "### 3. 竞争优势\n\n"
    for usp in response.core_shell_point.product_usp:
        markdown_data += f"  - {usp}\n\n"
    markdown_data += "### 4. 品牌关键词\n\n"
    key_words = " ".join(response.core_shell_point.keywords_to_include)
    markdown_data += "```Text\n"
    markdown_data += f"{key_words}\n\n"
    markdown_data += "```\n\n"

    markdown_data += "## 剧情大纲\n\n"
    reset_title_list = []
    for script_item in response.slot_script:
        item = {}
        item['开始时间'] = script_item.start_time
        item['结束时间'] = script_item.end_time
        item['段落主题'] = script_item.paragraph_theme
        item['画面描述'] = script_item.screen_description

        actor_lines = "   ".join(actor.role_name + ":" + actor.lines for actor in script_item.actor_lines)
        item['台词'] = actor_lines
        reset_title_list.append(item)
    df = pd.DataFrame(reset_title_list)
    markdown_scene_table = df.to_markdown(index=False)
    markdown_data += markdown_scene_table
    markdown_data += "\n\n"

    markdown_path_str = dir_path + f'/clone_{clone_script_id}.md'
    markdown_path = Path(markdown_path_str)

    if markdown_path.is_file():  # 确保是文件且存在（如果是目录，此方法返回 False）
        markdown_path.unlink()   # 删除文件
        print(f"文件 {markdown_path} 已成功删除")
    # else:
    #     print(f"{markdown_path_str} 文件不存在，无需操作")
    
    with open(markdown_path, 'w', encoding='utf-8') as f:
        f.write(markdown_data)
    return markdown_path_str


async def creative_slot_background(state: CloneState):
    from app.services.llm import creative_system_prompt, creative_model
    db = SessionLocal()
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        video = db.query(Video).filter(Video.id == state['video_id']).first()

        dir_path = settings.UPLOAD_DIR + f'/{state["video_id"]}'
        make_dir(dir_path, re_create=False)
        quary = f"""
请根据以下输入，执行阶段一的创意换血任务：

1. 原视频分析文本
```Markdown
{state['ori_parameters'].get('analysis_focus')}
```

2. 原视频剧情大纲
```Json
{state['ori_parameters'].get('plot_script')}
```

3. 全新主题/产品梗概（Clone Theme）
```Text
{state['clone_theme']}
```

请开始你的创意创作：
"""
        print(f'quary: {quary}')
        messages = [
            SystemMessage(creative_system_prompt),
            HumanMessage(quary)
        ]
        response = await creative_model.ainvoke(messages)
        if not isinstance(response, CloneAnalysis):
            raise Exception("llm输出格式错误")
        json_response = response.model_dump_json()
        print(f"json_response: {json_response}")
        messages.append(AIMessage(json_response))

        md_path = await convert_clone_to_md(response, dir_path, state['clone_script_id'])
        
        clone_script.clone_parse_file_path = md_path
        clone_script.clone_parse_pointer = json_response

        video.clone_progress = 10

        db.commit() 

        return {
            "creative_messages": messages
        }
    except Exception as e:
        message = f'创建脚本背景时发生错误 {str(e)}'
        return Command(
            # state update
            update={'error': message},
            # control flow
            goto="process_error"
        )
    finally:
        db.close()


async def is_complete(state: CloneState) -> Literal["process_error", END]:
    error_message = state['error']
    if error_message:
        print(f'error_message: {error_message}')
        return "process_error"
    return END

async def process_error(state: CloneState):
    await send_fail_status(state['video_id'], state['error'])
    return {}

async def send_fail_status(video_id: int, error: str):
    db = SessionLocal()
    try:
        print(f'occur error {error}')
        video = db.query(Video).filter(Video.id == video_id).first()
        if not video:
            raise
        video.clone_status = CloneStatus.CLONE_FAILED
        video.error_message = error
        db.commit()
    except Exception as e:
        video = db.query(Video).filter(Video.id == video_id).first()
        if video:
            video.status = CloneStatus.CLONE_FAILED
            video.error_message = str(e)
            db.commit()
        raise
    finally:
        db.close()

clone_graph_builder = StateGraph(CloneState)

clone_graph_builder.add_node("get_ori_context", get_ori_context)
clone_graph_builder.add_node("creative_slot_background", creative_slot_background)
clone_graph_builder.add_node("process_error", process_error)

clone_graph_builder.add_edge(START, "get_ori_context")
clone_graph_builder.add_edge("get_ori_context", "creative_slot_background")
clone_graph_builder.add_conditional_edges(
    "creative_slot_background",
    is_complete,
    ["process_error", END]
)
clone_graph_builder.add_edge("process_error", END)

clone_graph = clone_graph_builder.compile(checkpointer=False)

async def begin_clone(video_id: int, theme: str, step: int=1):
    try:
        initial_input = {
            "creative_messages": [],
            "clone_theme": theme,
            "video_id": video_id,
            "guide": None,
            "clone_script_id": -1,
            "error": "" 
        }
        await clone_graph.ainvoke(initial_input)
    except Exception as e:
        await send_fail_status(video_id=video_id, error=str(e))

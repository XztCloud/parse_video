import copy
from pathlib import Path

from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
import operator
from typing import Annotated, Literal, TypedDict

from langgraph.types import Command
from langgraph.graph import END, START, StateGraph
import pandas as pd
from pydantic import BaseModel, ValidationError
from langchain_core.exceptions import OutputParserException
from sqlalchemy import delete, select
from app.models.script import CloneStatus

from app.database import AsyncSessionLocal, SessionLocal
from app.models.script import CloneScript, Script
from app.models.video import Video
from app.services.llm import REDUCE_LINES_PROMPT, CloneAnalysis, ReduceLines, reduce_lines_model
from app.util import calculate_duration_units, make_dir
from app.config import settings
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)

class VideScript(TypedDict):
    analysis_focus: str     # 分析重点
    plot_script: str        # 剧情脚本
    storyboard: list[dict] | None  # 分镜信息列表
    width: int
    height: int
    duration: float
    

class ClonePlotState(TypedDict):
    # creative_messages: Annotated[list[AnyMessage], operator.add] # 仅用于保存创意llm对话，因为会跨节点
    ori_parameters: VideScript    # 原视频分析得到的参数
    clone_parameters: VideScript  # 复刻后的视频参数
    clone_script_id: int # 复刻脚本id
    error: str


async def get_ori_context(state: ClonePlotState) -> Command[Literal['process_error', 'creative_plot_background']]:
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
            clone_script = result.scalar_one_or_none()
            result = await db.execute(select(Script).where(Script.id == clone_script.script_id))
            script = result.scalar_one_or_none()
            if not clone_script or not script:
                raise Exception('原始脚本不存在，请先解析再复刻')
            
            
            clone_script.clone_progress = 5
            await db.commit()
            ori_parameters = VideScript(
                analysis_focus=script.parse_pointer,
                plot_script=script.parse_script,
                storyboard=None,
                width=540,
                height=720,
                duration=32.0
            )
            return Command(
                update={"ori_parameters": ori_parameters},
                goto='creative_plot_background'
            )
            
        except Exception as e:
            logger.exception('get_ori_context failed')
            message = f'获取原始脚本节点发生错误 {str(e)}'
            return Command(
                update={'error': message},
                goto="process_error"
            )


async def convert_clone_to_md(response: CloneAnalysis, dir_path: str, clone_script_id: int) -> str:
    markdown_data = "# 视频脚本\n\n"
    markdown_data += "## 剧情人物\n\n"

    reset_title_list = []
    for role in response.role_library:
        item = {}
        item['名称'] = role.role_name
        item['性别'] = '男' if role.gender == 'male' else '女'
        item['年龄'] = role.age
        item['声音'] = role.voice_style_guide if role.voice_style_guide else '不发声'
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
    for script_item in response.plot_script:
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
        logger.info(f"文件 {markdown_path} 已成功删除")
    
    with open(markdown_path, 'w', encoding='utf-8') as f:
        f.write(markdown_data)
    return markdown_path_str


async def creative_struct_output(analysis_focus, plot_script, clone_theme):
    from app.services.llm import CREATIVE_SYSTEM_PROMPT, CREATIVE_QUERY_PROMPT, creative_model, creative_model_strict
    error_message = ''
    try:
        query =  CREATIVE_QUERY_PROMPT.format(
            analysis_focus=analysis_focus,
            plot_script=plot_script,
            clone_theme=clone_theme,
            error_message=''
        )
        logger.info(f'query: {query}')
        messages = [
            SystemMessage(CREATIVE_SYSTEM_PROMPT),
            HumanMessage(query)
        ]
        response = await creative_model.ainvoke(
            messages,
            config={
                "configurable": {
                    "temperature":1.0
                }
            })
        return response

    except (ValidationError, OutputParserException) as e:
        # 🚨 进到这里，说明百分之百是大模型格式崩了 / 吐出的 JSON 畸形
        logger.error(f"【特定捕获】大模型生成格式错误，无法解析为指定的 Pydantic 模型。错误详情: {e}")
        
        # 判定并记录更详细的错误原因
        if isinstance(e, ValidationError):
            error_message = "Pydantic 校验失败（可能是大模型漏掉字段、写错类型或JSON截断）"
            logger.warning("具体原因为：Pydantic 校验失败（可能是大模型漏掉字段、写错类型或JSON截断）")
        elif isinstance(e, OutputParserException):
            error_message = "LangChain 解析器崩溃（大模型可能吐出了纯文本或Markdown，压根不是JSON）"
            logger.warning("具体原因为：LangChain 解析器崩溃（大模型可能吐出了纯文本或Markdown，压根不是JSON）")

    except Exception as e:
        # 其他异常（比如：OpenAI 接口网络超时、API 余额不足、Key 错了等）
        logger.error(f"【其他错误】非格式问题导致的常规网络或API异常: {e}")
        raise e
    
    query =  CREATIVE_QUERY_PROMPT.format(
        analysis_focus=analysis_focus,
        plot_script=plot_script,
        clone_theme=clone_theme,
        error_message=error_message
    )
    logger.info(f'strict query: {query}')
    messages = [
        SystemMessage(CREATIVE_SYSTEM_PROMPT),
        HumanMessage(query)
    ]
    response = await creative_model_strict.ainvoke(
        messages,
        config={
            "configurable": {
                "temperature":1.0
            }
        })
    return response

async def creative_plot_background(state: ClonePlotState) -> Command[Literal['process_error', '__end__']]:
    # from app.services.llm import CREATIVE_SYSTEM_PROMPT, CREATIVE_QUERY_PROMPT, creative_model
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
            clone_script = result.scalar_one_or_none()

            dir_path = settings.UPLOAD_DIR + f'/clone_{clone_script.id}'
            make_dir(dir_path)

            response = await creative_struct_output(
                analysis_focus=state['ori_parameters'].get('analysis_focus'),
                plot_script=state['ori_parameters'].get('plot_script'),
                clone_theme=clone_script.clone_theme
            )
            response = CloneAnalysis.model_validate(response)
            if not isinstance(response, CloneAnalysis):
                raise Exception("llm输出格式错误")
            
            logger.info(f'ori CloneAnalysis: {response.model_dump_json()}')
            for plot in response.plot_script:
                plot_duration = plot.end_time - plot.start_time
                lines_duration = sum(lines.predict_duration for lines in plot.actor_lines)
                if lines_duration > plot_duration:
                    # TODO:使用重试策略替代
                    raise Exception(f"llm预估时长错误, {lines_duration} > {plot_duration}")
            
            # 估算时长，修改对话文本
            for item_script in response.plot_script:
                item_script_duration = item_script.end_time - item_script.start_time
                # llm_predict_duration = 0.0
                lines_duration_list = []

                for item_lines in item_script.actor_lines:
                    text = item_lines.lines

                    calc_result = calculate_duration_units(text)
                    char_count=calc_result['char_count']
                    punc_count=calc_result['punc_count']
                    
                    duration_units = (char_count+punc_count*0.3) / 4.5

                    logger.info(f'\ntext:{text}, \nduration_units:{duration_units}, char_count:{char_count}, punc_count: {punc_count}')
                    lines_duration_list.append(duration_units)

                predict_duration = sum(lines_duration_list)
                logger.info(f'plot duration: {item_script_duration}, calc duration:{predict_duration}')
                if predict_duration > item_script_duration:
                    item_script_dict = item_script.model_dump()
                    query = REDUCE_LINES_PROMPT.format(
                        ori_lines=item_script_dict['actor_lines'],
                        ori_duration=predict_duration,
                        targe_duration=item_script_duration
                    )
                    logger.info(f'query:{query}')

                    reduce_lines = await reduce_lines_model.ainvoke(
                        [HumanMessage(query)],
                        config={
                            "configurable": {
                                "temperature":0.1
                            }
                        })
                    if not isinstance(reduce_lines, ReduceLines):
                        raise Exception("llm输出格式错误")

                    item_script.actor_lines = copy.deepcopy(reduce_lines.actor_lines)

                    logger.info(f'检查到台词超长，简化了台词')
                    logger.info(f'\n原台词：{item_script_dict['actor_lines']} \n\n修改后台词：{reduce_lines.model_dump()}')


            logger.info(f'convert_clone_to_md response is {response}')
            md_path = await convert_clone_to_md(response, dir_path, state['clone_script_id'])
            
            json_response = response.model_dump_json()
            logger.info(f"json_response: {json_response}")

            clone_script.clone_parse_file_path = md_path
            clone_script.clone_parse_pointer = json_response
            clone_script.clone_progress = 20
            clone_script.clone_status = CloneStatus.PLOT_DONE
            await db.commit() 

            return Command(
                goto='__end__'
            )
        except Exception as e:
            message = f'创建脚本背景时发生错误 {str(e)}'
            logger.exception('创建脚本背景时发生错误')
            return Command(
                update={'error': message},
                goto="process_error"
            )

async def process_error(state: ClonePlotState):
    await send_fail_status(state['clone_script_id'], state['error'])

async def send_fail_status(clone_script_id: int, error: str):
    async with AsyncSessionLocal() as db:
        try:
            logger.info(f'occur error {error}')
            result = await db.execute(select(CloneScript).where(CloneScript.id == clone_script_id))
            clone_script = result.scalar_one_or_none()
            if not clone_script:
                logger.info(f'clone_script is none.')
            clone_script.clone_status = CloneStatus.FAILED
            clone_script.clone_error_message = error
            await db.commit()
        except Exception as e:
            logger.exception('发生异常')
            logger.error(f'send_fail_status error {e}')

clone_plot_graph_builder = StateGraph(ClonePlotState)

clone_plot_graph_builder.add_node("get_ori_context", get_ori_context)
clone_plot_graph_builder.add_node("creative_plot_background", creative_plot_background)
clone_plot_graph_builder.add_node("process_error", process_error)

clone_plot_graph_builder.add_edge(START, "get_ori_context")
clone_plot_graph_builder.add_edge("process_error", END)

clone_plot_graph = clone_plot_graph_builder.compile(checkpointer=False)

import copy
from pathlib import Path

from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
import operator
from typing import Annotated, Literal, TypedDict

from langgraph.types import Command
from langgraph.graph import END, START, StateGraph
import pandas as pd
from pydantic import BaseModel
from app.models.script import CloneStatus

from app.database import SessionLocal
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
    db = SessionLocal()
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        script = db.query(Script).filter(Script.id == clone_script.script_id).first()
        if not clone_script or not script:
            raise Exception('原始脚本不存在，请先解析再复刻')
        clone_script.clone_progress = 5
        clone_script.clone_status = CloneStatus.PLOT
        db.commit()
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
        logger.info(f'get_ori_context failed. {e}')
        message = f'获取原始脚本节点发生错误 {str(e)}'
        return Command(
            update={'error': message},
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


async def creative_plot_background(state: ClonePlotState) -> Command[Literal['process_error', '__end__']]:
    from app.services.llm import CREATIVE_SYSTEM_PROMPT, CREATIVE_QUERY_PROMPT, creative_model
    db = SessionLocal()
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        # video = db.query(Video).filter(Video.id == state['video_id']).first()

        dir_path = settings.UPLOAD_DIR + f'/clone_{clone_script.id}'
        make_dir(dir_path)

        query =  CREATIVE_QUERY_PROMPT.format(
            analysis_focus=state['ori_parameters'].get('analysis_focus'),
            plot_script=state['ori_parameters'].get('plot_script'),
            clone_theme=clone_script.clone_theme,
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

        # response_debug = {
        #     "role_library": [
        #         {
        #             "role_name": "旁白",
        #             "gender": "male",
        #             "age": 32,
        #             "voice_style_guide": "沉稳专业，富有亲和力，语速适中",
        #             "effect": "负责产品信息输出、核心价值传递，最终引导用户完成购买决策"
        #         },
        #         {
        #             "role_name": "出镜消费者",
        #             "gender": "female",
        #             "age": 26,
        #             "voice_style_guide": None,
        #             "effect": "作为目标用户的具象化呈现，强化产品真实使用场景感知"
        #         }
        #     ],
        #     "scene_library": [
        #         {
        #             "scene_name": "冰蓝水源开场场景",
        #             "environment_description": "中心是带发光农夫山泉标识的长白山天然水源冰晶体，背景是流动的清透山泉水流，地面铺有细密的水波纹路与冷调扩散光效，通过推镜放大冰晶体强化纯净感知",
        #             "color_grading": "冰蓝色，高通透度，冷调清新"
        #         },
        #         {
        #             "scene_name": "清透水晕品质矩阵场景",
        #             "environment_description": "以清透的淡蓝水晕为背景，用透明几何造型分别代表水源甄选、多层净化、无菌灌装、品控检测等核心品质环节，银蓝色发光线路串联各环节呈现完整保障链路",
        #             "color_grading": "淡蓝透白，柔和光泽，清新自然"
        #         },
        #         {
        #             "scene_name": "白领办公实景场景",
        #             "environment_description": "现代简约的开放办公区，年轻白领伏案工作，手边摆放着农夫山泉饮用纯净水，桌面有柔和的自然光",
        #             "color_grading": "冷白调，明亮通透，生活化质感"
        #         },
        #         {
        #             "scene_name": "水质细节演示场景",
        #             "environment_description": "农夫山泉饮用纯净水的产品特写，依次展示清透无杂质的水体、密封锁鲜的瓶盖、清晰的质检标识",
        #             "color_grading": "冰蓝色，高清晰度，突出纯净质感"
        #         },
        #         {
        #             "scene_name": "冰蓝水纹收尾场景",
        #             "environment_description": "以流动延伸的冰蓝色水波纹为背景，突出带银白描边的立体产品名称，搭配柔和的冷光效",
        #             "color_grading": "冰蓝色，渐变柔光，高级质感"
        #         }
        #     ],
        #     "global_style": {
        #         "global_style_suffix": "cinematic lighting, photorealistic, 4k resolution, fresh natural style, high clarity"
        #     },
        #     "core_shell_point": {
        #         "user_pain_point": "日常饮水担心水质不纯、有安全隐患，选水既想要纯净安心又想要性价比高，适配多场景使用",
        #         "product_usp": [
        #             "源自优质天然水源地，多层净化工艺保障水质纯净无杂质",
        #             "适配办公、居家、出行等全场景饮用，无需改变日常饮水习惯",
        #             "亲民定价，整箱购买性价比更高，满足日常高频补水需求",
        #             "全链路严格品控，符合国家饮用纯净水标准，饮用更安心"
        #         ],
        #         "hook_trigger": "黄金3秒用极致纯净的长白山水源冰晶体特写抓人，直观传递「纯净安全」核心特质，引发用户对健康饮水的需求共鸣",
        #         "keywords_to_include": [
        #             "农夫山泉",
        #             "饮用纯净水",
        #             "天然水源",
        #             "纯净安全",
        #             "高性价比"
        #         ]
        #     },
        #     "plot_script": [
        #         {
        #             "start_time": 0.0,
        #             "end_time": 10.4,
        #             "paragraph_theme": "产品品质官宣与全场景适配能力介绍",
        #             "screen_description": "采用冰蓝清新自然风格，全程固定品牌统一标识：顶部农夫山泉logo、左侧竖排「天然水源 饮用更安心」提示；开篇展示长白山天然水源冰晶体，官宣农夫山泉饮用纯净水源自优质水源地，随后说明产品适配办公、居家、出行等全场景饮用需求，用户无需改变日常饮水习惯",
        #             "actor_lines": [
        #                 {
        #                     "role_name": "旁白",
        #                     "predict_duration": 8.5,
        #                     "lines": "重磅！农夫山泉饮用纯净水源自优质天然水源地。除此之外，适配办公、居家、出行全场景，无需改变日常饮水习惯。",
        #                     "audio_style": "沉稳专业/亲和/播音腔"
        #                 }
        #             ]
        #         },
        #         {
        #             "start_time": 10.4,
        #             "end_time": 20.5,
        #             "paragraph_theme": "全链路品质保障矩阵核心能力展示",
        #             "screen_description": "延续清透水晕清新风格，保留品牌统一标识；展示以「水源地甄选」为核心，覆盖多层净化、无菌灌装、严格品控、锁鲜包装等全链路品质保障矩阵，直观呈现每一瓶水的安全保障体系",
        #             "actor_lines": [
        #                 {
        #                     "role_name": "旁白",
        #                     "predict_duration": 9.0,
        #                     "lines": "不仅有核心水源地甄选保障，还覆盖多层净化、无菌灌装、严格品控、锁鲜包装等全链路品质保障矩阵，每一瓶都安全放心。",
        #                     "audio_style": "沉稳专业/亲和/播音腔"
        #                 }
        #             ]
        #         },
        #         {
        #             "start_time": 20.5,
        #             "end_time": 25.3,
        #             "paragraph_theme": "高性价比定价与纯净品质细节演示",
        #             "screen_description": "延续清新自然风格，保留品牌统一标识；先呈现白领日常办公饮水场景，介绍单瓶亲民定价、整箱购买更划算的高性价比权益，随后通过清透无杂质的水质、密封锁鲜瓶盖的特写，演示产品满足日常高频安全补水需求的能力",
        #             "actor_lines": [
        #                 {
        #                     "role_name": "旁白",
        #                     "predict_duration": 4.3,
        #                     "lines": "亲民定价整箱购更划算，满足日常高频安全补水需求。",
        #                     "audio_style": "沉稳专业/亲和/播音腔"
        #                 }
        #             ]
        #         },
        #         {
        #             "start_time": 25.3,
        #             "end_time": 32.0,
        #             "paragraph_theme": "价值总结与购买引导",
        #             "screen_description": "采用冰蓝水纹清新风格，保留品牌统一标识；以流动延伸的冰蓝色水波纹为背景，点明产品「喝得安心、喝得放心」的核心价值，定位为日常饮水的安心之选，引导用户点击下方链接选购",
        #             "actor_lines": [
        #                 {
        #                     "role_name": "旁白",
        #                     "predict_duration": 6.0,
        #                     "lines": "现在点击下方链接选购，让饮水回归纯粹，喝得安心放心。农夫山泉是你日常饮水的安心之选。",
        #                     "audio_style": "沉稳专业/亲和/播音腔"
        #                 }
        #             ]
        #         }
        #     ]
        # }
        response = CloneAnalysis.model_validate(response)
        if not isinstance(response, CloneAnalysis):
            raise Exception("llm输出格式错误")
        
        for plot in response.plot_script:
            plot_duration = plot.end_time - plot.start_time
            lines_duration = sum(lines.predict_duration for lines in plot.actor_lines)
            if lines_duration > plot_duration:
                # TODO:使用重试策略替代
                raise Exception("llm预估时长错误")

        

        

        # 估算时长，修改对话文本
        for item_script in response.plot_script:
            item_script_duration = item_script.end_time - item_script.start_time
            # llm_predict_duration = 0.0
            lines_duration_list = []

            for item_lines in item_script.actor_lines:
                text = item_lines.lines
                # cn_count = len(re.findall(r'[\u4e00-\u9fff]', text))
                # en_words = re.findall(r"[A-Za-z']+", text)
                # en_count = len(en_words) 
                
                # duration_units = cn_count + en_count * 0.6

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
                
                # reduce_lines_duration = sum(lines.predict_duration for lines in reduce_lines.actor_lines)
                # if reduce_lines_duration > item_script_duration * 1.15:
                #     # TODO:增加重试方案
                #     logger.info(f'\n原台词：{item_script_dict['actor_lines']} \n\n修改后台词：{reduce_lines.model_dump()}')
                #     logger.info(f'简化台词后，时长不正确，不采用该简化方案！！！')
                #     continue
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
        db.commit() 

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
    finally:
        db.close()

async def process_error(state: ClonePlotState):
    await send_fail_status(state['clone_script_id'], state['error'])

async def send_fail_status(clone_script_id: int, error: str):
    db = SessionLocal()
    try:
        logger.info(f'occur error {error}')
        clone_script = db.query(CloneScript).filter(CloneScript.id == clone_script_id).first()
        if not clone_script:
            logger.info(f'clone_script is none.')
        clone_script.clone_status = CloneStatus.FAILED
        clone_script.clone_error_message = error
        db.commit()
    except Exception as e:
        logger.exception('发生异常')
        logger.info(f'send_fail_status error {e}')
    finally:
        db.close()

clone_plot_graph_builder = StateGraph(ClonePlotState)

clone_plot_graph_builder.add_node("get_ori_context", get_ori_context)
clone_plot_graph_builder.add_node("creative_plot_background", creative_plot_background)
clone_plot_graph_builder.add_node("process_error", process_error)

clone_plot_graph_builder.add_edge(START, "get_ori_context")
clone_plot_graph_builder.add_edge("process_error", END)

clone_plot_graph = clone_plot_graph_builder.compile(checkpointer=False)

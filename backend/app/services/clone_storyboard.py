

import asyncio
import inspect
import json
import os
import shutil
import tempfile
import traceback
from typing import List, Literal, TypedDict
import httpx
from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.types import Command
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, TypeAdapter
from pydub import AudioSegment
from pydub.playback import play
from sqlalchemy import delete, select

from app.config import settings
from app.services.llm import ActorLines, AudioTimeline, CharacterAsset, CharacterManifest, CloneAnalysis, ReloadLines, ReloadLinesPrompt, Segment, StoryBoard, reload_lines_model
from app.database import AsyncSessionLocal, SessionLocal
from app.models.script import CloneScript, CloneScriptSegment, CloneStatus, CloneVoice
from app.services.clone_plot import send_fail_status
from app.services.gen_image import GenImage, GenImageParams, ImageSize
from app.util import calculate_duration_units, get_md5, make_dir
from app.services.gen_voice import GenVoice, GenVoiceParam, Lines
from langchain_core.runnables import RunnableConfig

from app.models.voice import VoiceInfoCollect
from app.services.predict.predict_voice_duration import PredictVoiceDuration

from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)

SCENE_VOICE_CIRCLE_MAX = 3

# class CustomStoryboardContext:
#     """自定义上下文，存放共享对象"""
#     gen_voice: GenVoice = None

# class VoiceSeekInfo(BaseModel):
#     seek_plot_idx: int = Field(default=0, description='遍历场景index')
#     lines_infos: list[list[Lines]] = Field(description='每个场景的台词列表')
#     plot_duration_list: list[float] = Field(description='每个场景的目标时长')
#     # gen_voice: GenVoice = Field(description='下载声音类对象')
#     save_dir: str
#     ratio: float = Field(default=1.0, description='实际声音时长/目标时长')
#     circle_num:int = Field(default=0, description='但场景音频循环获取次数')


class CloneStoryboardState(TypedDict):
    clone_script_id: int
    storyboard_script: StoryBoard | None # 分镜脚本
    plot_role_library: dict    # 上个节点得到的人物信息
    plot_scene_library: dict    # 上个节点得到的场景信息
    character_manifest: CharacterManifest | None # 人物生图提示词
    role_asset_library: dict # 角色资产信息列表
    scene_asset_library: dict # 场景资产信息列表
    # voice_seek_info: VoiceSeekInfo # 声音遍历信息
    error: str
    retry_cnt: int  # 分镜不合规重试次数
    retry_messages: str # 检查到的不符合预期的数据合集

def log_node_start():
    # [1] 代表上一层调用者的堆栈帧
    caller_name = inspect.stack()[1].function
    logger.info(f"======== 🚀 LangGraph 节点开始执行: [{caller_name}] ========")

async def generate_storyboard(state: CloneStoryboardState):
    from app.services.llm import STORYBOARD_SYSTEM_PROMPT, STORYBOARD_QUERY_PROMPT, storyboard_model
    log_node_start()
    db = AsyncSessionLocal()
    try:
        statment = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
        clone_script = statment.scalar_one_or_none()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')

        await db.execute(delete(CloneScriptSegment).where(CloneScriptSegment.script_id == state['clone_script_id']))

        clone_script.clone_progress = 31
        await db.commit()


        plot_script = json.loads(clone_script.clone_parse_pointer)
        # logger.info(f'plot_script is {plot_script},   type is {type(plot_script)}')
        # return Command(goto="__end__") 
        query = STORYBOARD_QUERY_PROMPT.format(
            plot_script=plot_script,
            notice=state['retry_messages']
        )
        logger.info(f'query: {query}')
        messages = [SystemMessage(STORYBOARD_SYSTEM_PROMPT),
                    HumanMessage(query)]
        response = await storyboard_model.ainvoke(
            messages,
            config={
                "configurable": {
                    "temperature":0.0
                }
            }
        )
        if not isinstance(response, StoryBoard):
            raise Exception("generate_storyboard llm输出格式错误")
        
        json_str_res = response.model_dump_json()
        logger.info(f'generate storyboard is {json_str_res}')
        logger.info(f'set plot_role_library is {plot_script.get('role_library', [])}')
        logger.info(f'set plot_scene_library is {plot_script.get('scene_library', [])}')


        return Command(
            update={
                'storyboard_script': response,
                'plot_role_library': plot_script.get('role_library', []),
                'plot_scene_library': plot_script.get('scene_library', [])
            },
            goto='check_storyboard_result'
        )
    except Exception as e:
        error_message = f'generate_storyboard failed. {str(e)}'
        logger.info(error_message)
        logger.exception('generate_storyboard 发生错误')
        return Command(
            update={'error': error_message},
            goto='process_error'
        )
    finally:
        await db.close()


async def check_storyboard_result(state: CloneStoryboardState):
    log_node_start()
    # db = SessionLocal()
    try:
        
        # clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        plot_role_name = [role['role_name'] for role in state['plot_role_library'] if 'role_name' in role]
        plot_scene_name = [scene['scene_name'] for scene in state['plot_scene_library'] if 'scene_name' in scene]
        storyboard_script = state['storyboard_script']
        logger.info(f'plot_role_name:{plot_role_name}, plot_scene_name:{plot_scene_name}')

        extra_scene_messages = ''
        extra_role_messages = ''
        for segments in storyboard_script.segments:
            if segments.scene_name not in plot_scene_name:
                logger.info(f'find scene_name:{segments.scene_name} not in plot_scene_name')
                extra_scene_messages += f'发现剧本中存在场景名({segments.scene_name}) 不在视频脚本（来自创意总监的宏观设想）中 \n'
            for lines in segments.audio_timeline:
                if lines.role_name not in plot_role_name:
                    logger.info(f'find role_name:{lines.role_name} not in plot_role_name')
                    extra_role_messages += f'发现剧本中存在人物名({lines.role_name}) 不在视频脚本（来自创意总监的宏观设想）中 \n'

        
        retry_messages= ''
        if extra_scene_messages:
            retry_messages = '# 请重新对齐场景\n\n' + extra_scene_messages
        
        if extra_role_messages:
            retry_messages = '# 请重新对齐人物\n\n' + extra_role_messages
        
        if retry_messages:
            logger.info(f'extra_role_messages: {extra_role_messages}')
        retry_cnt = state.get('retry_cnt', 0)
        
        return {
            'retry_messages': retry_messages,
            'retry_cnt': retry_cnt + 1
            }
        
    except Exception as e:
        error_message = f'check_storyboard_result failed. {str(e)}'
        logger.info(error_message)
        logger.exception('check_storyboard_result 发生错误')
        # 静态边 强制到 need_retry_storyboard
        return {
            'retry_messages': error_message,
            'error': error_message,
            'retry_cnt': settings.STORYBOARD_TRY_COUNT+1
        }

async def need_retry_storyboard(state: CloneStoryboardState):
    retry_max = settings.STORYBOARD_TRY_COUNT
    retry_cnt = state.get('retry_cnt', 0)
    if state['retry_messages']:
        if retry_cnt <= retry_max:
            return 'generate_storyboard'
        return 'process_error'
    return 'reset_segment_duration'




async def reset_segment_duration(state: CloneStoryboardState):
    """检查每个分镜的时长，是否符合生成视频的时长限制 """
    log_node_start()
    db = AsyncSessionLocal()
    try:
        statment = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
        clone_script = statment.scalar_one_or_none()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        # TODO: 检查每个分镜的时长，是否符合生成视频的时长限制，不符合的单独切分
        

        return Command(goto='save_storyboard')
    except Exception as e:
        await db.rollback()
        error_message = f'reset_segment_duration failed. {str(e)}'
        logger.info(error_message)
        logger.exception('reset_segment_duration 切分分镜出错')
        return Command(
            update={'error': error_message},
            goto="process_error"
        )
    finally:
        await db.close()


async def save_storyboard(state: CloneStoryboardState):
    log_node_start()
    db = AsyncSessionLocal()
    async def add_voice_path(lines_list: List[AudioTimeline]):
        statment = await db.execute(select(CloneVoice).where(CloneVoice.script_id == state['clone_script_id']))
        clone_voice_list = statment.scalars().all()
        # clone_voice_list = db.query(CloneVoice).filter(CloneVoice.script_id == state['clone_script_id']).all()
        list_of_dicts = [item.model_dump() for item in lines_list]
        if not clone_voice_list:
            return list_of_dicts
        for lines_dict in list_of_dicts:
            # 1. 计算要查台词的 MD5
            search_md5 = get_md5(lines_dict['lines'])

            # 2. 精准命中联合索引查询
            statment = await db.execute(select(CloneVoice.path).where(
                CloneVoice.role_name == lines_dict['role_name'],
                CloneVoice.text_md5 == search_md5,
                CloneVoice.voice_type == lines_dict['audio_style']))
            result = statment.scalars().first()

            # result = db.query(CloneVoice.path).filter(
            #     CloneVoice.role_name == lines_dict['role_name'],
            #     CloneVoice.text_md5 == search_md5,
            #     CloneVoice.voice_type == lines_dict['audio_style']
            # ).first()
            if result:
                audio_path = result
                lines_dict['audio_path'] = audio_path
                logger.info(f"找到音频路径: {audio_path}")
            else:
                logger.error("未找到对应音频")
                raise Exception(f'未找到台词【{lines_dict['lines']}】对应的音频')
            
        return list_of_dicts


    try:
        statment = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
        clone_script = statment.scalar_one_or_none()
        # clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        storyboard_script = state['storyboard_script']
        offset_time = 0.0
        for segment in storyboard_script.segments:
            dialogue = await add_voice_path(segment.audio_timeline)
            logger.info(f'dialogue is {dialogue}')
            clone_segement = CloneScriptSegment(
                script_id=state['clone_script_id'],
                start_time=round(offset_time, 2),
                end_time=round(offset_time+segment.duration_budget, 2),
                shot_description=segment.prompt_for_video,
                dialogue=dialogue,
                segment_type=segment.target_emotion
            )
            offset_time = round(offset_time+segment.duration_budget, 2)
            db.add(clone_segement)
        
        clone_script.clone_progress = 35
        clone_script.clone_status = CloneStatus.SEGMENTS_DONE
        await db.commit()

        return Command(goto='__end__')
    except Exception as e:
        await db.rollback()
        error_message = f'save_storyboard failed. {str(e)}'
        logger.info(error_message)
        logger.exception('save_storyboard 切分分镜出错')
        return Command(
            update={'error': error_message},
            goto="process_error"
        )
    finally:
        await db.close()
    


async def process_error(state: CloneStoryboardState):
    log_node_start()
    retry_max = settings.STORYBOARD_TRY_COUNT
    retry_cnt = state.get('retry_cnt', 0)
    if not state['error'] and retry_cnt > retry_max:
        await send_fail_status(state['clone_script_id'], '重试次数超过限制')
    else:
        await send_fail_status(state['clone_script_id'], state['error'])
    logger.info('process_error')



clone_storyboard_builder = StateGraph(CloneStoryboardState)



clone_storyboard_builder.add_node('generate_storyboard', generate_storyboard)
clone_storyboard_builder.add_node('check_storyboard_result', check_storyboard_result)
clone_storyboard_builder.add_node('reset_segment_duration', reset_segment_duration)
clone_storyboard_builder.add_node('save_storyboard', save_storyboard)
clone_storyboard_builder.add_node('process_error', process_error)


clone_storyboard_builder.add_edge(START, 'generate_storyboard')

clone_storyboard_builder.add_conditional_edges(
    'check_storyboard_result',
    need_retry_storyboard,
    ['generate_storyboard', 'process_error', 'reset_segment_duration']
)

clone_storyboard_builder.add_edge('process_error', END)

clone_storyboard_graph = clone_storyboard_builder.compile(checkpointer=False)
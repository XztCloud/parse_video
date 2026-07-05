

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

from app.config import settings
from app.services.llm import ActorLines, AudioTimeline, CharacterAsset, CharacterManifest, CloneAnalysis, ReloadLines, ReloadLinesPrompt, Segment, StoryBoard, reload_lines_model
from app.database import SessionLocal
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


# async def preload_lines_voices(state: CloneStoryboardState, config: RunnableConfig):
#     ''' 文本转音频前的准备操作 '''
#     log_node_start()
#     db = SessionLocal()
#     try:
#         clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
#         if not clone_script or not clone_script.clone_parse_pointer:
#             raise Exception('not find clone_script in generate_storyboard')
        
#         parse_pointer = json.loads(clone_script.clone_parse_pointer)

#         role_library = parse_pointer['role_library']

#         # 1. 获取角色信息
#         voice_param_dict = {}
#         for role_info in role_library:
#             role_name = role_info['role_name']
#             item = GenVoiceParam(
#                 role_name=role_name,
#                 gender=role_info['gender'],
#                 age=role_info['age'],
#                 voice_desc=role_info['voice_style_guide'],
#                 lines_list=[]
#             )
#             voice_param_dict[role_name] = item

#         # 2. 按照 role_name 和 场景 收集对应角色的台词
#         plot_script_list = parse_pointer['plot_script']

#         lines_infos = []
#         plot_duration_list = []
#         for plot_script in plot_script_list:
#             plot_duration = plot_script['end_time'] - plot_script['start_time']
#             plot_duration_list.append(plot_duration)
#             plot_lines_infos = []
#             for actor_lines in plot_script['actor_lines']:
#                 item = voice_param_dict.get(actor_lines['role_name'], None)
#                 if not isinstance(item, GenVoiceParam):
#                     raise Exception(f'role_name not found, {actor_lines['role_name']}')
#                 item.lines_list.append(actor_lines['lines'])

#                 plot_lines_infos.append(
#                     Lines(
#                         role_name=actor_lines['role_name'],
#                         audio_style=actor_lines['audio_style'],
#                         text=actor_lines['lines'],
#                         target_duration=actor_lines['predict_duration']
#                     )
#                 )
#             lines_infos.append(plot_lines_infos)
        

#         # 3.下载音频前准备操作
#         save_dir = settings.UPLOAD_DIR + '/clone_' + str(state['clone_script_id'])
#         make_dir(save_dir, re_create=False)

#         # 从 config 中获取上下文
#         context: CustomStoryboardContext = config.get("configurable", {}).get("context")
#         if not context:
#             raise ValueError("GenVoice 未初始化")
#         gen_voice = context.gen_voice
#         # 获取所有支持的音色列表
#         await gen_voice.get_voice_list()
        
#         # 根据角色相关信息选择对应音色
#         for gen_voice_param in voice_param_dict.values():
#             if gen_voice_param.voice_desc is None:
#                 logger.info(f'{gen_voice_param.role_name} 没有台词，略过')
#                 continue
#             await gen_voice.filter_voices(role_voice=gen_voice_param)

#             logger.info(f'GenVoiceParam is {gen_voice_param.model_dump_json()}')

#         voice_seek_info = VoiceSeekInfo(
#             seek_plot_idx=0,
#             lines_infos=lines_infos,
#             plot_duration_list=plot_duration_list,
#             save_dir=save_dir
#         )

#         clone_script.clone_progress = 22
#         db.commit() 

#         logger.info(f'voice_seek_info is {voice_seek_info.model_dump_json()}')

#         return Command(
#             update={
#                 'voice_seek_info': voice_seek_info
#             },
#             goto='download_voices'
#         )

#     except Exception as e:
#         error_message = f'generate_storyboard failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('preload_lines_voices 预处理下载音频发生错误')
#         return Command(
#             update={'error': error_message},
#             goto='process_error'
#         )
#     finally:
#         db.close()

# async def download_voices(state:CloneStoryboardState, config: RunnableConfig):
#     log_node_start()
#     db = SessionLocal()
#     try:
#         voice_seek_info = state['voice_seek_info']
#         if not isinstance(voice_seek_info, VoiceSeekInfo):
#             raise Exception('voice_seek_info not init')
        
#         circle_num = voice_seek_info.circle_num
#         if circle_num >= SCENE_VOICE_CIRCLE_MAX:
#             raise Exception('circle over limited')
        
#         voice_seek_info.circle_num += 1

#         seek_plot_idx = voice_seek_info.seek_plot_idx
#         if seek_plot_idx >= len(voice_seek_info.lines_infos) or \
#             seek_plot_idx >= len(voice_seek_info.plot_duration_list):
#             raise Exception('voice seek out limit')
#         cur_scene_lines = voice_seek_info.lines_infos[seek_plot_idx]

#         context: CustomStoryboardContext = config.get("configurable", {}).get("context")
#         if not context:
#             raise ValueError("GenVoice 未初始化")
        
#         for lines in cur_scene_lines:
#             predict_duration = await asyncio.to_thread(PredictVoiceDuration.predict_model, spk_id=lines.audio_style, next_text=lines.text)
#             if predict_duration == -1:
#                 continue
#             logger.info(f'spk_id:{lines.audio_style} 预测文本：{lines.text}， 预测时长：{predict_duration}， 目标时长：{lines.target_duration}')
#             # TODO: 按照句子进行文本修改。加减速等

#         gen_voice = context.gen_voice
#         save_dir = voice_seek_info.save_dir + '/voice_plot_' + str(voice_seek_info.seek_plot_idx)
#         make_dir(save_dir)

#         await gen_voice.dwonload_voice(lines_voices=cur_scene_lines, save_dir=save_dir)

#         plot_target_duration = voice_seek_info.plot_duration_list[seek_plot_idx]
#         plot_voice_duration = sum(lines.duration for lines in cur_scene_lines)

#         # 记录下载音频信息
#         for lines in cur_scene_lines:
            
#             calc_result = calculate_duration_units(lines.text)
#             voice_info = VoiceInfoCollect(
#                 spk_id=lines.spk_id,
#                 text=lines.text,
#                 char_count=calc_result['char_count'],
#                 punc_count=calc_result['punc_count'],
#                 audio_duration=round(lines.duration, 2)
#             )

#             db.add(voice_info)
#             db.commit()
#             db.refresh(voice_info)

#         ratio = (
#             plot_voice_duration
#             / plot_target_duration
#         )
#         logger.info(f'ratio is {ratio}')
#         voice_seek_info.ratio = ratio
#         return {'voice_seek_info': voice_seek_info}
#     except Exception as e:
#         error_message = f'generate_storyboard failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('download_voices 下载音频发生错误')
#         return {'error': error_message}
#     finally:
#         db.close()
    

# async def shourld_reset_voice_duration(state:CloneStoryboardState):
#     log_node_start()
#     voice_seek_info = state['voice_seek_info']
#     seek_plot_idx = voice_seek_info.seek_plot_idx
#     cur_scene_lines = voice_seek_info.lines_infos[seek_plot_idx]

#     if state['error']:
#         return 'process_error'
    
#     ratio = voice_seek_info.ratio

#     if len(cur_scene_lines) == 0 or ratio == 0:
#         logger.info('本场景没有台词')
#         return 'next_scene_voice'
    
#     if ratio >= 1.25:
#         # 压缩文本重新TTS
#         return 'reload_scene_lines'
#     elif ratio >= 1.05:
#         # 调整语速重新TTS
#         return 'reset_speach_rate'
#     elif ratio >= 0.95:
#         return 'next_scene_voice'
#     elif ratio >= 0.9:
#         # 微调语速 
#         return 'reset_speach_rate'
#     elif ratio >= 0.75:
#         # 均补静音
#         return 'next_scene_voice'

#     # 缩短镜头
#     return 'next_scene_voice'


# async def reset_lines_duration(state: CloneStoryboardState):
#     ''' 重新设置每句话的时长 '''
#     db = SessionLocal()
#     try:
#         clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
#         if not clone_script or not clone_script.clone_parse_pointer:
#             raise Exception('not find clone_script in generate_storyboard')
        
#         voice_seek_info = state['voice_seek_info']
#         if not isinstance(voice_seek_info, VoiceSeekInfo):
#             raise Exception('voice_seek_info not init')
#         real_lines_duration = []
#         for plot_lines in voice_seek_info.lines_infos:
#             for lines in plot_lines:
#                 real_lines_duration.append(lines.duration)

#         parse_pointer = CloneAnalysis.model_validate_json(clone_script.clone_parse_pointer)
#         plot_script_list = parse_pointer.plot_script
        
#         cnt = 0
#         for plot_script in plot_script_list:
#             for actor_lines in plot_script.actor_lines:
#                 if cnt >= len(real_lines_duration):
#                     raise Exception('lines number > voice number')
#                 actor_lines.predict_duration = real_lines_duration[cnt]
#                 cnt += 1
#         clone_script.clone_parse_pointer = parse_pointer.model_dump_json()
#         db.commit()

#     except Exception as e:
#         error_message = f'reset_lines_duration failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('reset_lines_duration 重置台词时长发生错误')
#         raise e
#     finally:
#         db.close()


# async def save_voice_info(state: CloneStoryboardState):
#     db = SessionLocal()
#     try:
#         voice_seek_info = state['voice_seek_info']
#         if not isinstance(voice_seek_info, VoiceSeekInfo):
#             raise Exception('voice_seek_info not init')
#         clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
#         if not clone_script or not clone_script.clone_parse_pointer:
#             raise Exception('not find clone_script in generate_storyboard')
#         for plot_voices in voice_seek_info.lines_infos:
#             for voice in plot_voices:
#                 clone_voice = CloneVoice(
#                     script_id=state['clone_script_id'], 
#                     role_name=voice.role_name,
#                     duration=voice.duration,
#                     voice_type=voice.audio_style,
#                     path=str(voice.audio_path.absolute()))
#                 db.add(clone_voice)
        
#         clone_script.clone_status = CloneStatus.VOICE_DONE
#         clone_script.clone_progress = 30

#         db.commit()
                
#     except Exception as e:
#         db.rollback()
#         raise e
#     finally:
#         db.close()


# async def next_scene_voice(state:CloneStoryboardState):
#     log_node_start()
#     try:
#         voice_seek_info = state['voice_seek_info']
#         if not isinstance(voice_seek_info, VoiceSeekInfo):
#             raise Exception('voice_seek_info not init')
        
#         voice_seek_info.circle_num = 0
#         next_plot_idx = voice_seek_info.seek_plot_idx + 1
#         logger.info(f'场景{voice_seek_info.seek_plot_idx}音频获取完成，next场景：{next_plot_idx}')
#         voice_seek_info.seek_plot_idx = next_plot_idx

#         # 场景遍历结束
#         if voice_seek_info.seek_plot_idx >= len(voice_seek_info.lines_infos):
#             logger.info(f'所有场景音频获取完成')
#             await reset_lines_duration(state=state)

#             await save_voice_info(state=state)

#             return Command(
#                 goto='generate_storyboard'
#             )
#         else:
#             return Command(
#                 update={'voice_seek_info': voice_seek_info},
#                 goto='download_voices'
#             )

#     except Exception as e:
#         error_message = f'generate_storyboard failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('next_scene_voice 发生错误')
#         return Command(
#             update={'error': error_message},
#             goto='process_error'
#         )


# async def reload_scene_lines(state: CloneStoryboardState):
#     log_node_start()
#     try:
#         voice_seek_info = state['voice_seek_info']
#         if not isinstance(voice_seek_info, VoiceSeekInfo):
#             raise Exception('voice_seek_info not init')
#         seek_plot_idx = voice_seek_info.seek_plot_idx
#         if seek_plot_idx >= len(voice_seek_info.lines_infos) or \
#             seek_plot_idx >= len(voice_seek_info.plot_duration_list):
#             raise Exception('voice seek out limit')
        
#         plot_target_duration = voice_seek_info.plot_duration_list[seek_plot_idx]
#         cur_scene_lines = voice_seek_info.lines_infos[seek_plot_idx]
#         cur_lines_dict = [{'role_name': lines.role_name, 'text': lines.text} for lines in cur_scene_lines]

#         logger.info(f'before reload, lines: {cur_lines_dict}')

#         plot_voice_duration = sum(lines.duration for lines in cur_scene_lines)
#         query = ReloadLinesPrompt.format(
#             plot_target_duration=plot_target_duration,
#             plot_voice_duration=plot_voice_duration,
#             compress_ratio=voice_seek_info.ratio,
#             scene_text=cur_lines_dict
#         )
#         logger.info(f'reload lines query: {query}')

#         messages = [HumanMessage(query)]
#         retry_cnt = 0
#         error_message = ''
#         while retry_cnt < 3:
#             reload_lines = await reload_lines_model.ainvoke(messages)
#             if not isinstance(reload_lines, ReloadLines):
#                 messages.append(AIMessage(reload_lines))
#                 error_message = '返回格式错误，请按照执行结构输出'
#             elif len(reload_lines.actor_lines) != len(cur_scene_lines):
#                 messages.append(AIMessage(reload_lines.model_dump_json))
#                 error_message = '台词数目不正确，禁止增减台词数目！重新生成'
            
#             if error_message:
#                 logger.info(f'error_message is {error_message}')
#                 messages.append(HumanMessage(error_message))
#                 error_message = ''
#             else:
#                 break
#             retry_cnt += 1

#         if retry_cnt >= 3:
#             raise Exception('重新设置台词失败')

#         for i, lines in enumerate(cur_scene_lines):
#             lines.text = reload_lines.actor_lines[i].text
        
#         logger.info(f'after reload, lines is {voice_seek_info.lines_infos[seek_plot_idx]}')

#         return Command(
#             update={'voice_seek_info': voice_seek_info},
#             goto='download_voices'
#         )

#     except Exception as e:
#         error_message = f'generate_storyboard failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('reload_scene_lines 发生错误')
#         return Command(
#             update={'error': error_message},
#             goto='process_error'
#         )


# async def reset_speach_rate(state: CloneStoryboardState):
#     """ 调整音频速度 """
#     log_node_start()
#     try:
#         voice_seek_info = state['voice_seek_info']
#         ratio = voice_seek_info.ratio
#         seek_plot_idx = voice_seek_info.seek_plot_idx
#         cur_scene_lines = voice_seek_info.lines_infos[seek_plot_idx]
#         for lines in cur_scene_lines:
            
#             # 加载音频
#             audio = AudioSegment.from_file(lines.audio_path)

#             # 调速：speed=1.5 表示加速50%
#             changed_audio = audio.speedup(playback_speed=ratio)
#             with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
#                 temp_path = tmp.name
#                 logger.info(f"💾 导出到临时文件: {temp_path}")
#                 changed_audio.export(temp_path, format="mp3")
#             # 保存
#             shutil.move(temp_path, lines.audio_path)
#             logger.info(f"✅ 覆盖成功: {lines.audio_path}")

#         return Command(
#             update={'voice_seek_info': voice_seek_info},
#             goto='next_scene_voice'
#         )
#     except Exception as e:
#         error_message = f'reset_speach_rate failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('reset_speach_rate 发生错误')
#         return Command(
#             update={'error': error_message},
#             goto='process_error'
#         )




async def generate_storyboard(state: CloneStoryboardState):
    from app.services.llm import STORYBOARD_SYSTEM_PROMPT, STORYBOARD_QUERY_PROMPT, storyboard_model
    log_node_start()
    db = SessionLocal()
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')

        clone_script.clone_status = CloneStatus.SEGMENTS
        clone_script.clone_progress = 31
        db.commit()


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
        db.close()


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
    db = SessionLocal()
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        # TODO: 检查每个分镜的时长，是否符合生成视频的时长限制，不符合的单独切分


        return Command(goto='save_storyboard')
    except Exception as e:
        db.rollback()
        error_message = f'reset_segment_duration failed. {str(e)}'
        logger.info(error_message)
        logger.exception('reset_segment_duration 切分分镜出错')
        return Command(
            update={'error': error_message},
            goto="process_error"
        )
    finally:
        db.close()


async def save_storyboard(state: CloneStoryboardState):
    log_node_start()

    def add_voice_path(lines_list: List[AudioTimeline]):
        clone_voice_list = db.query(CloneVoice).filter(CloneVoice.script_id == state['clone_script_id']).all()
        list_of_dicts = [item.model_dump() for item in lines_list]
        if not clone_voice_list:
            return list_of_dicts
        for lines_dict in list_of_dicts:
            # 1. 计算要查台词的 MD5
            search_md5 = get_md5(lines_dict['lines'])

            # 2. 精准命中联合索引查询
            result = db.query(CloneVoice.path).filter(
                CloneVoice.role_name == lines_dict['role_name'],
                CloneVoice.text_md5 == search_md5,
                CloneVoice.voice_type == lines_dict['audio_style']
            ).first()
            if result:
                audio_path = result[0]
                lines_dict['audio_path'] = audio_path
                logger.info(f"找到音频路径: {audio_path}")
            else:
                logger.error("未找到对应音频")
                raise Exception(f'未找到台词【{lines_dict['lines']}】对应的音频')
            
        return list_of_dicts


    db = SessionLocal()
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        storyboard_script = state['storyboard_script']
        offset_time = 0.0
        for segment in storyboard_script.segments:
            dialogue = add_voice_path(segment.audio_timeline)
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
        db.commit()

        return Command(goto='__end__')
    except Exception as e:
        db.rollback()
        error_message = f'save_storyboard failed. {str(e)}'
        logger.info(error_message)
        logger.exception('save_storyboard 切分分镜出错')
        return Command(
            update={'error': error_message},
            goto="process_error"
        )
    finally:
        db.close()
    
   

# async def abstract_role_info(state: CloneStoryboardState):
#     from app.services.llm import PRODUCER_QUERY_PROMPT, PRODUCER_SYSTEM_PROMPT, producer_model
#     log_node_start()
#     db=SessionLocal()
#     try:
#         clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
#         if not clone_script or not clone_script.clone_parse_pointer:
#             raise Exception('not find clone_script in generate_storyboard')
        
#         clone_script.clone_progress = 36
#         clone_script.clone_status = CloneStatus.IMAGE
#         db.commit()
        
#         storyboard = state['storyboard_script']
#         storyboard_json = storyboard.model_dump()
#         query = PRODUCER_QUERY_PROMPT.format(
#             role_library=state['plot_role_library'],
#             storyboard=storyboard_json
#         )
#         messages = [SystemMessage(PRODUCER_SYSTEM_PROMPT),
#                     HumanMessage(query)]
#         response = await producer_model.ainvoke(
#             messages,
#             config={
#                 "configurable": {
#                     "temperature":0.7
#                 }
#             }
#         )
#         if not isinstance(response, CharacterManifest):
#             raise Exception("abstract_role_info llm输出格式错误")

#         logger.info(f'abstract_role_info output: {response.model_dump_json()}')

#         return Command(
#             update={'character_manifest': response},
#             goto='check_role_info'
#         )

#     except Exception as e:
#         error_message = f'generate_storyboard failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('abstract_role_info 生成任务详情出错')
#         return Command(
#             update={'error': error_message},
#             goto="process_error"
#         )
#         # return {'error': f'generate_storyboard failed. {str(e)}'}
#     finally:
#         db.close()

# async def check_role_info(state: CloneStoryboardState):
#     log_node_start()
#     try:
#         plot_role_name = [role['role_name'] for role in state['plot_role_library'] if 'role_name' in role]
#         character_manifest = state['character_manifest']
#         logger.info(f'plot_role_name:{plot_role_name}')


#         extra_role_messages = ''
#         for character in character_manifest.character_list:
#             if character.role_name not in plot_role_name:
#                 logger.info(f'find role_name:{character.role_name} not in plot_role_name')
#                 extra_role_messages += f'发现剧本中存在人物名({character.role_name}) 不在视频脚本中 \n'
        
#         retry_messages=''
#         if extra_role_messages:
#             retry_messages = '# 请重新对齐人物\n\n' + extra_role_messages
        
#         if retry_messages:
#             logger.info(f'extra_role_messages: {extra_role_messages}')
#         retry_cnt = state.get('retry_cnt', 0)
        
#         return {
#             'retry_messages': retry_messages,
#             'retry_cnt': retry_cnt + 1
#             }

#     except Exception as e:
#         error_message = f'check_storyboard_result failed. {str(e)}'
#         logger.info(error_message)
#         logger.exception('check_role_info 发生错误')
#         return {
#             'retry_messages':error_message,
#             'error': error_message,
#             'retry_cnt': settings.STORYBOARD_TRY_COUNT + 1
#         }
#         return Command(
#             update={'error': error_message},
#             goto="process_error"
#         )

# async def need_retry_abstract(state: CloneStoryboardState):
#     retry_max = settings.STORYBOARD_TRY_COUNT
#     retry_cnt = state.get('retry_cnt', 0)
#     if state['retry_messages']:
#         if retry_cnt <= retry_max:
#             return 'abstract_role_info'
#         return 'process_error'
#     return 'initial_images'

# async def initial_images(state: CloneStoryboardState) -> Command[Literal['initial_videos', 'process_error']]:
#     """
#     生成图片
#     """
#     log_node_start()
#     db = SessionLocal()
#     try:
#         character_manifest = state['character_manifest']
#         if not isinstance(character_manifest, CharacterManifest):
#             raise Exception('character_manifest is None.')
        
#         clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
#         if not clone_script or not clone_script.clone_parse_pointer:
#             raise Exception('not find clone_script in generate_storyboard')
        
#         gen_image = GenImage()

#         save_dir = settings.UPLOAD_DIR + '/clone_' + str(state['clone_script_id'])
#         make_dir(save_dir, re_create=False)

#         role_img_info = {}
#         for character in character_manifest.character_list:
#             if character.visual_anchor_prompt:
#                 params = GenImageParams(
#                     prompt=character.visual_anchor_prompt,
#                     image_size=ImageSize.SIZE_1024x1024.value
#                 )
#                 image_path_list = await gen_image.gen_image(gen_image_params=params, save_dir=save_dir, prefix=character.role_name)
#                 logger.info(f'get image path list: {image_path_list}')
#                 # if len(image_path_list) > 0:
#                 role_img_info[character.role_name] = image_path_list

#         # TODO: 增加生成每个分镜首帧的图片

#         clone_script.clone_status = CloneStatus.IMAGE_DONE
#         clone_script.clone_progress = 50
#         db.commit()
                    
#         return Command(goto='initial_videos')
#     except Exception as e:
#         error_message = f'initial_images failed. {str(e)}'
#         logger.exception('initial_images 发生错误')
#         logger.info(error_message)

#         return Command(
#             update={'error': error_message},
#             goto="process_error"
#         )
    

# async def initial_videos(state: CloneStoryboardState):
#     """
#     开始创建视频
#     """
#     log_node_start()
#     pass

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

# clone_storyboard_builder.add_node('preload_lines_voices', preload_lines_voices)
# clone_storyboard_builder.add_node('download_voices', download_voices)
# clone_storyboard_builder.add_node('next_scene_voice', next_scene_voice)
# clone_storyboard_builder.add_node('reload_scene_lines', reload_scene_lines)
# clone_storyboard_builder.add_node('reset_speach_rate', reset_speach_rate)

clone_storyboard_builder.add_node('generate_storyboard', generate_storyboard)
clone_storyboard_builder.add_node('check_storyboard_result', check_storyboard_result)
clone_storyboard_builder.add_node('reset_segment_duration', reset_segment_duration)
clone_storyboard_builder.add_node('save_storyboard', save_storyboard)
# clone_storyboard_builder.add_node('abstract_role_info', abstract_role_info)
# clone_storyboard_builder.add_node('check_role_info', check_role_info)
# clone_storyboard_builder.add_node('initial_images', initial_images)
# clone_storyboard_builder.add_node('initial_videos', initial_videos)
clone_storyboard_builder.add_node('process_error', process_error)

# clone_storyboard_builder.add_edge(START, 'preload_lines_voices')
# clone_storyboard_builder.add_conditional_edges(
#     'download_voices',
#     shourld_reset_voice_duration,
#     ['process_error', 'next_scene_voice', 'reload_scene_lines', 'reset_speach_rate']
# )

clone_storyboard_builder.add_edge(START, 'generate_storyboard')

clone_storyboard_builder.add_conditional_edges(
    'check_storyboard_result',
    need_retry_storyboard,
    ['generate_storyboard', 'process_error', 'reset_segment_duration']
)

# clone_storyboard_builder.add_conditional_edges(
#     'check_role_info',
#     need_retry_abstract,
#     ['abstract_role_info', 'process_error', 'initial_images']
# )

# clone_storyboard_builder.add_edge('initial_videos', 'process_error')
clone_storyboard_builder.add_edge('process_error', END)

clone_storyboard_graph = clone_storyboard_builder.compile(checkpointer=False)
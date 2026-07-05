

import asyncio
import inspect
import json
import shutil
import tempfile
from typing import TypedDict

from celery.utils.log import get_task_logger
from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command
from app.services.gen_voice import GenVoice, GenVoiceParam, Lines
from app.database import SessionLocal
from app.models.script import CloneScript, CloneStatus, CloneVoice
from app.config import settings
from app.util import calculate_duration_units, get_md5, make_dir
from app.models.voice import VoiceInfoCollect
from app.services.clone_plot import send_fail_status
from app.services.llm import CloneAnalysis, ReloadLinesPrompt
from app.services.predict.predict_voice_duration import PredictVoiceDuration
from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from app.services.llm import ReloadLines, reload_lines_model
from pydub import AudioSegment


logger = get_task_logger(__name__)

SCENE_VOICE_CIRCLE_MAX = 3

class CustomVoiceContext:
    """自定义上下文，存放共享对象"""
    gen_voice: GenVoice = None

class VoiceSeekInfo(BaseModel):
    seek_plot_idx: int = Field(default=0, description='遍历场景index')
    lines_infos: list[list[Lines]] = Field(description='每个场景的台词列表')
    plot_duration_list: list[float] = Field(description='每个场景的目标时长')
    save_dir: str
    ratio: float = Field(default=1.0, description='实际声音时长/目标时长')
    circle_num:int = Field(default=0, description='但场景音频循环获取次数')

class CloneVoiceState(TypedDict):
    clone_script_id: int
    voice_seek_info: VoiceSeekInfo | None # 声音遍历信息
    error: str


def log_node_start():
    # [1] 代表上一层调用者的堆栈帧
    caller_name = inspect.stack()[1].function
    logger.info(f"======== 🚀 LangGraph 节点开始执行: [{caller_name}] ========")


async def preload_lines_voices(state: CloneVoiceState, config: RunnableConfig):
    ''' 文本转音频前的准备操作 '''
    log_node_start()
    db = SessionLocal()
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        parse_pointer = json.loads(clone_script.clone_parse_pointer)

        role_library = parse_pointer['role_library']

        # 1. 获取角色信息
        voice_param_dict = {}
        for role_info in role_library:
            role_name = role_info['role_name']
            item = GenVoiceParam(
                role_name=role_name,
                gender=role_info['gender'],
                age=role_info['age'],
                voice_desc=role_info['voice_style_guide'],
                lines_list=[]
            )
            voice_param_dict[role_name] = item

        # 2. 按照 role_name 和 场景 收集对应角色的台词
        plot_script_list = parse_pointer['plot_script']

        lines_infos = []
        plot_duration_list = []
        for plot_script in plot_script_list:
            plot_duration = plot_script['end_time'] - plot_script['start_time']
            plot_duration_list.append(plot_duration)
            plot_lines_infos = []
            for actor_lines in plot_script['actor_lines']:
                item = voice_param_dict.get(actor_lines['role_name'], None)
                if not isinstance(item, GenVoiceParam):
                    raise Exception(f'role_name not found, {actor_lines['role_name']}')
                item.lines_list.append(actor_lines['lines'])

                plot_lines_infos.append(
                    Lines(
                        role_name=actor_lines['role_name'],
                        audio_style=actor_lines['audio_style'],
                        text=actor_lines['lines'],
                        target_duration=actor_lines['predict_duration']
                    )
                )
            lines_infos.append(plot_lines_infos)
        

        # 3.下载音频前准备操作
        save_dir = settings.UPLOAD_DIR + '/clone_' + str(state['clone_script_id'])
        make_dir(save_dir, re_create=False)

        # 从 config 中获取上下文
        context: CustomVoiceContext = config.get("configurable", {}).get("context")
        if not context:
            raise ValueError("GenVoice 未初始化")
        gen_voice = context.gen_voice
        # 获取所有支持的音色列表
        await gen_voice.get_voice_list()
        
        # 根据角色相关信息选择对应音色
        for gen_voice_param in voice_param_dict.values():
            if gen_voice_param.voice_desc is None:
                logger.info(f'{gen_voice_param.role_name} 没有台词，略过')
                continue
            await gen_voice.filter_voices(role_voice=gen_voice_param)

            logger.info(f'GenVoiceParam is {gen_voice_param.model_dump_json()}')

        voice_seek_info = VoiceSeekInfo(
            seek_plot_idx=0,
            lines_infos=lines_infos,
            plot_duration_list=plot_duration_list,
            save_dir=save_dir
        )

        clone_script.clone_status = CloneStatus.VOICE
        clone_script.clone_progress = 21
        db.commit() 

        logger.info(f'voice_seek_info is {voice_seek_info.model_dump_json()}')

        return Command(
            update={
                'voice_seek_info': voice_seek_info
            },
            goto='download_voices'
        )

    except Exception as e:
        error_message = f'generate_storyboard failed. {str(e)}'
        logger.info(error_message)
        logger.exception('preload_lines_voices 预处理下载音频发生错误')
        return Command(
            update={'error': error_message},
            goto='process_error'
        )
    finally:
        db.close()

async def download_voices(state:CloneVoiceState, config: RunnableConfig):
    log_node_start()
    db = SessionLocal()
    try:
        voice_seek_info = state['voice_seek_info']
        if not isinstance(voice_seek_info, VoiceSeekInfo):
            raise Exception('voice_seek_info not init')
        
        circle_num = voice_seek_info.circle_num
        if circle_num >= SCENE_VOICE_CIRCLE_MAX:
            raise Exception('circle over limited')
        
        voice_seek_info.circle_num += 1

        seek_plot_idx = voice_seek_info.seek_plot_idx
        if seek_plot_idx >= len(voice_seek_info.lines_infos) or \
            seek_plot_idx >= len(voice_seek_info.plot_duration_list):
            raise Exception('voice seek out limit')
        cur_scene_lines = voice_seek_info.lines_infos[seek_plot_idx]

        context: CustomVoiceContext = config.get("configurable", {}).get("context")
        if not context:
            raise ValueError("GenVoice 未初始化")
        
        for lines in cur_scene_lines:
            predict_duration = await asyncio.to_thread(PredictVoiceDuration.predict_model, spk_id=lines.audio_style, next_text=lines.text)
            if predict_duration == -1:
                continue
            logger.info(f'spk_id:{lines.audio_style} 预测文本：{lines.text}， 预测时长：{predict_duration}， 目标时长：{lines.target_duration}')
            # TODO: 按照句子进行文本修改。加减速等

        gen_voice = context.gen_voice
        save_dir = voice_seek_info.save_dir + '/voice_plot_' + str(voice_seek_info.seek_plot_idx)
        make_dir(save_dir)

        await gen_voice.dwonload_voice(lines_voices=cur_scene_lines, save_dir=save_dir)

        plot_target_duration = voice_seek_info.plot_duration_list[seek_plot_idx]
        plot_voice_duration = sum(lines.duration for lines in cur_scene_lines)

        # 记录下载音频信息
        for lines in cur_scene_lines:
            
            calc_result = calculate_duration_units(lines.text)
            voice_info = VoiceInfoCollect(
                spk_id=lines.spk_id,
                text=lines.text,
                char_count=calc_result['char_count'],
                punc_count=calc_result['punc_count'],
                audio_duration=round(lines.duration, 2)
            )

            db.add(voice_info)
            db.commit()
            db.refresh(voice_info)

        ratio = (
            plot_voice_duration
            / plot_target_duration
        )
        logger.info(f'ratio is {ratio}')
        voice_seek_info.ratio = ratio
        return {'voice_seek_info': voice_seek_info}
    except Exception as e:
        error_message = f'generate_storyboard failed. {str(e)}'
        logger.info(error_message)
        logger.exception('download_voices 下载音频发生错误')
        return {'error': error_message}
    finally:
        db.close()
    

async def shourld_reset_voice_duration(state:CloneVoiceState):
    log_node_start()
    voice_seek_info = state['voice_seek_info']
    seek_plot_idx = voice_seek_info.seek_plot_idx
    cur_scene_lines = voice_seek_info.lines_infos[seek_plot_idx]

    if state['error']:
        return 'process_error'
    
    ratio = voice_seek_info.ratio

    if len(cur_scene_lines) == 0 or ratio == 0:
        logger.info('本场景没有台词')
        return 'next_scene_voice'
    
    if ratio >= 1.25:
        # 压缩文本重新TTS
        return 'reload_scene_lines'
    elif ratio >= 1.05:
        # 调整语速重新TTS
        return 'reset_speach_rate'
    elif ratio >= 0.95:
        return 'next_scene_voice'
    elif ratio >= 0.9:
        # 微调语速 
        return 'reset_speach_rate'
    elif ratio >= 0.75:
        # 均补静音
        return 'next_scene_voice'

    # 缩短镜头
    return 'next_scene_voice'


async def reset_lines_duration(state: CloneVoiceState):
    ''' 重新设置每句话的时长 '''
    db = SessionLocal()
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        voice_seek_info = state['voice_seek_info']
        if not isinstance(voice_seek_info, VoiceSeekInfo):
            raise Exception('voice_seek_info not init')
        real_lines_duration = []
        for plot_lines in voice_seek_info.lines_infos:
            for lines in plot_lines:
                real_lines_duration.append(lines.duration)

        parse_pointer = CloneAnalysis.model_validate_json(clone_script.clone_parse_pointer)
        plot_script_list = parse_pointer.plot_script
        
        cnt = 0
        for plot_script in plot_script_list:
            for actor_lines in plot_script.actor_lines:
                if cnt >= len(real_lines_duration):
                    raise Exception('lines number > voice number')
                actor_lines.predict_duration = real_lines_duration[cnt]
                cnt += 1
        clone_script.clone_parse_pointer = parse_pointer.model_dump_json()
        db.commit()

    except Exception as e:
        error_message = f'reset_lines_duration failed. {str(e)}'
        logger.info(error_message)
        logger.exception('reset_lines_duration 重置台词时长发生错误')
        raise e
    finally:
        db.close()


async def save_voice_info(state: CloneVoiceState):
    db = SessionLocal()
    try:
        voice_seek_info = state['voice_seek_info']
        if not isinstance(voice_seek_info, VoiceSeekInfo):
            raise Exception('voice_seek_info not init')
        clone_script = db.query(CloneScript).filter(CloneScript.id == state['clone_script_id']).first()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        sort_order = 1
        for plot_voices in voice_seek_info.lines_infos:
            for voice in plot_voices:
                clone_voice = CloneVoice(
                    script_id=state['clone_script_id'], 
                    role_name=voice.role_name,
                    duration=voice.duration,
                    voice_type=voice.audio_style,
                    spk_id=voice.spk_id,
                    path=str(voice.audio_path.absolute()),
                    text=voice.text,
                    text_md5=get_md5(voice.text),
                    sort_order=sort_order,
                )
                sort_order += 1
                db.add(clone_voice)
        
        clone_script.clone_status = CloneStatus.VOICE_DONE
        clone_script.clone_progress = 30

        db.commit()
                
    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


async def next_scene_voice(state:CloneVoiceState):
    log_node_start()
    try:
        voice_seek_info = state['voice_seek_info']
        if not isinstance(voice_seek_info, VoiceSeekInfo):
            raise Exception('voice_seek_info not init')
        
        voice_seek_info.circle_num = 0
        next_plot_idx = voice_seek_info.seek_plot_idx + 1
        logger.info(f'场景{voice_seek_info.seek_plot_idx}音频获取完成，next场景：{next_plot_idx}')
        voice_seek_info.seek_plot_idx = next_plot_idx

        # 场景遍历结束
        if voice_seek_info.seek_plot_idx >= len(voice_seek_info.lines_infos):
            logger.info(f'所有场景音频获取完成')
            await reset_lines_duration(state=state)

            await save_voice_info(state=state)

            return Command(
                goto='__end__'
            )
        else:
            return Command(
                update={'voice_seek_info': voice_seek_info},
                goto='download_voices'
            )

    except Exception as e:
        error_message = f'generate_storyboard failed. {str(e)}'
        logger.info(error_message)
        logger.exception('next_scene_voice 发生错误')
        return Command(
            update={'error': error_message},
            goto='process_error'
        )


async def reload_scene_lines(state: CloneVoiceState):
    log_node_start()
    try:
        voice_seek_info = state['voice_seek_info']
        if not isinstance(voice_seek_info, VoiceSeekInfo):
            raise Exception('voice_seek_info not init')
        seek_plot_idx = voice_seek_info.seek_plot_idx
        if seek_plot_idx >= len(voice_seek_info.lines_infos) or \
            seek_plot_idx >= len(voice_seek_info.plot_duration_list):
            raise Exception('voice seek out limit')
        
        plot_target_duration = voice_seek_info.plot_duration_list[seek_plot_idx]
        cur_scene_lines = voice_seek_info.lines_infos[seek_plot_idx]
        cur_lines_dict = [{'role_name': lines.role_name, 'text': lines.text} for lines in cur_scene_lines]

        logger.info(f'before reload, lines: {cur_lines_dict}')

        plot_voice_duration = sum(lines.duration for lines in cur_scene_lines)
        query = ReloadLinesPrompt.format(
            plot_target_duration=plot_target_duration,
            plot_voice_duration=plot_voice_duration,
            compress_ratio=voice_seek_info.ratio,
            scene_text=cur_lines_dict
        )
        logger.info(f'reload lines query: {query}')

        messages = [HumanMessage(query)]
        retry_cnt = 0
        error_message = ''
        while retry_cnt < 3:
            reload_lines = await reload_lines_model.ainvoke(messages)
            if not isinstance(reload_lines, ReloadLines):
                messages.append(AIMessage(reload_lines))
                error_message = '返回格式错误，请按照执行结构输出'
            elif len(reload_lines.actor_lines) != len(cur_scene_lines):
                messages.append(AIMessage(reload_lines.model_dump_json))
                error_message = '台词数目不正确，禁止增减台词数目！重新生成'
            
            if error_message:
                logger.info(f'error_message is {error_message}')
                messages.append(HumanMessage(error_message))
                error_message = ''
            else:
                break
            retry_cnt += 1

        if retry_cnt >= 3:
            raise Exception('重新设置台词失败')

        for i, lines in enumerate(cur_scene_lines):
            lines.text = reload_lines.actor_lines[i].text
        
        logger.info(f'after reload, lines is {voice_seek_info.lines_infos[seek_plot_idx]}')

        return Command(
            update={'voice_seek_info': voice_seek_info},
            goto='download_voices'
        )

    except Exception as e:
        error_message = f'generate_storyboard failed. {str(e)}'
        logger.info(error_message)
        logger.exception('reload_scene_lines 发生错误')
        return Command(
            update={'error': error_message},
            goto='process_error'
        )


async def reset_speach_rate(state: CloneVoiceState):
    """ 调整音频速度 """
    log_node_start()
    try:
        voice_seek_info = state['voice_seek_info']
        ratio = voice_seek_info.ratio
        seek_plot_idx = voice_seek_info.seek_plot_idx
        cur_scene_lines = voice_seek_info.lines_infos[seek_plot_idx]
        for lines in cur_scene_lines:
            
            # 加载音频
            audio = AudioSegment.from_file(lines.audio_path)

            # 调速：speed=1.5 表示加速50%
            changed_audio = audio.speedup(playback_speed=ratio)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
                temp_path = tmp.name
                logger.info(f"💾 导出到临时文件: {temp_path}")
                changed_audio.export(temp_path, format="mp3")
            # 保存
            shutil.move(temp_path, lines.audio_path)
            logger.info(f"✅ 覆盖成功: {lines.audio_path}")

        return Command(
            update={'voice_seek_info': voice_seek_info},
            goto='next_scene_voice'
        )
    except Exception as e:
        error_message = f'reset_speach_rate failed. {str(e)}'
        logger.info(error_message)
        logger.exception('reset_speach_rate 发生错误')
        return Command(
            update={'error': error_message},
            goto='process_error'
        )
    
async def process_error(state: CloneVoiceState):
    log_node_start()
    await send_fail_status(state['clone_script_id'], state['error'])
    logger.info('process_error')
    

clone_voice_builder = StateGraph(CloneVoiceState)

clone_voice_builder.add_node('preload_lines_voices', preload_lines_voices)
clone_voice_builder.add_node('download_voices', download_voices)
clone_voice_builder.add_node('next_scene_voice', next_scene_voice)
clone_voice_builder.add_node('reload_scene_lines', reload_scene_lines)
clone_voice_builder.add_node('reset_speach_rate', reset_speach_rate)

clone_voice_builder.add_node('process_error', process_error)


clone_voice_builder.add_edge(START, 'preload_lines_voices')
clone_voice_builder.add_conditional_edges(
    'download_voices',
    shourld_reset_voice_duration,
    ['process_error', 'next_scene_voice', 'reload_scene_lines', 'reset_speach_rate']
)

clone_voice_builder.add_edge('process_error', END)

clone_voice_graph = clone_voice_builder.compile(checkpointer=False)


from typing import TypedDict
from sqlalchemy import update

from app.services.clone_plot import clone_plot_graph, send_fail_status
from app.services.clone_storyboard import clone_storyboard_graph
from langgraph.graph import END, START, StateGraph
from app.services.gen_voice import GenVoice
from celery.utils.log import get_task_logger
from app.services.clone_voice import CustomVoiceContext, clone_voice_graph
from app.services.clone_image import clone_image_graph
from app.services.clone_segment_video import generate_segments_video, generate_segments_video_minimax_h3
from app.services.clone_frame import generate_segment_frame_prompt
from app.services.clone_merge_video import merge_segment_videos
from app.models.script import CloneScript, CloneStatus
from app.tasks.process_loop_manager import process_loop
from app.util import SEGMENT_BEGIN_PROGRESS

logger = get_task_logger(__name__)

class CloneState(TypedDict):
    clone_script_id: int # 复刻脚本id
    error: str
    step: int
    auto_run: bool  # 自动走流程
    cur_step: int
    stop_step: int  # 自动执行到该阶段为止（含）；默认 8 = 全流程，复刻剧本只跑到分镜则传 2


async def select_step(state: CloneState):
    return {}

async def should_select_next_step(state: CloneState):
    clone_script_id = state['clone_script_id']
    step = state['step']
    auto_run = state['auto_run']
    logger.info(f'start graph, clone_script_id:{clone_script_id}, step:{step}, auto_run:{auto_run}')
    if step == 1:
        return 'plot_generation'
    if step == 2:
        return 'storyboard_generation'
    if step == 3:
        return 'voice_generation'
    if step == 4:
        return 'image_base_generation'
    if step == 5:
        return 'segment_frame_generation'
    if step == 6:
        return 'video_generation'
    if step == 7:
        return 'video_merge'
    return END

async def plot_generation(state:CloneState):
    try:
        logger.info('begin run plot_generation')
        initial_input = {
            "clone_script_id": state["clone_script_id"],
            "error": ""
        }
        await clone_plot_graph.ainvoke(initial_input)
        return {
            "step": 2
        }
    except Exception as e:
        logger.info(f'catch error in plot_generation. {str(e)}')
        return {'error': str(e), 'cur_step': 1}

async def voice_generation(state: CloneState):
    try:
        logger.info('begin run voice_generation')
        context = CustomVoiceContext()
        gen_voice = GenVoice()
        context.gen_voice = gen_voice
        config = {
            "configurable": {
                "context": context
            }
        }
        initial_input = {
            "clone_script_id": state["clone_script_id"],
            "voice_seek_info": None,
            "error": ''
        }
        await clone_voice_graph.ainvoke(initial_input, config=config)
        return {
            'step': 4
        }
    except Exception as e:
        logger.info(f'catch error in storyboard_generation. {str(e)}')
        return {'error': str(e), 'cur_step': 3}

async def storyboard_generation(state: CloneState):
    try:
        logger.info('begin run storyboard_generation')
        # 手动 clone_phase(2) 时 API 层已把状态推进到 SEGMENTS；
        # 剧本(step1)+分镜自动连续流转时，这里在同一 worker 任务内补齐状态，
        # 保证前端轮询能看到“分镜创作中”，而非长时间停留在 PLOT_DONE。
        await _set_clone_stage(state['clone_script_id'], CloneStatus.SEGMENTS, SEGMENT_BEGIN_PROGRESS)

        initial_input = {
            "clone_script_id": state["clone_script_id"],
            "storyboard_script": None,
            "plot_role_library": {},
            "plot_scene_library": {},
            "character_manifest": None,
            "error": "",
            "retry_cnt": 0,
            "retry_messages": '',
            "require_voice": True,
        }
        await clone_storyboard_graph.ainvoke(initial_input)
        return {
            'step': 3
        }
    except Exception as e:
        logger.info(f'catch error in storyboard_generation. {str(e)}')
        return {'error': str(e), 'cur_step': 2}
    
async def image_base_generation(state: CloneState):
    try:
        logger.info('begin run image_base_generation')

        input_data = {
            "clone_script_id": state["clone_script_id"],
            "character_manifest": None,
            "role_asset_library": {},
            "scene_asset_library": {},
            "global_style": "",
            "retry_messages": "",
            "error": ""
        }

        await clone_image_graph.ainvoke(input_data)
        return {
            'step': 5
        }
    except Exception as e:
        logger.info(f'catch error in image_base_generation. {str(e)}')
        return {'error': str(e), 'cur_step': 4}
    
async def segment_frame_generation(state:CloneState):
    try:
        logger.info('begin run segment_frame_generation')
        # minimax_h3 ref 模型直接使用角色/场景参考图出视频，不逐镜生成分镜首帧；
        # generate_segment_frame_prompt 在该模式下仍会收尾把状态推进到 FRAME_DONE，
        # 必须调用它才能让 step5(参考帧) 阶段正常结束，否则 generate_flow_status 卡在 FRAME 一直“生成中”。
        await generate_segment_frame_prompt(state["clone_script_id"])
        return {
            'step': 6
        }
    except Exception as e:
        logger.info(f'catch error in segment_frame_generation. {str(e)}')
        return {'error': str(e), 'cur_step': 5}
    
async def video_generation(state: CloneState):
    try:
        logger.info('begin run video_generation')
        # 使用ltx2.3首尾帧生成视频
        # await generate_segments_video(state["clone_script_id"]
        # 使用minimax_h3 ref关联角色生成视频
        await generate_segments_video_minimax_h3(state["clone_script_id"])
        return {
            'step': 7
        }

    except Exception as e:
        logger.info(f'catch error in video_generation. {str(e)}')
        return {'error': str(e), 'cur_step': 6}

async def video_merge(state: CloneState):
    try:
        logger.info('begin run video_merge')
        await merge_segment_videos(state["clone_script_id"])
        return {
            'step': 8
        }

    except Exception as e:
        logger.info(f'catch error in video_merge. {str(e)}')
        return {'error': str(e), 'cur_step': 7}
    

async def should_continue(state: CloneState):
    if state['error']:
        return 'process_error'
    # 阶段节点返回的下一个 step 不超过 stop_step 才继续自动流转，
    # 从而支持「复刻剧本只自动跑 剧本+分镜」停在 SEGMENTS_DONE。
    if state['auto_run'] and int(state.get('step', 0)) <= int(state.get('stop_step', 8)):
        return 'select_step'
    return END


async def _set_clone_stage(clone_script_id: int, status: CloneStatus, progress: int):
    """推进 clone_status/clone_progress（供自动流转时在阶段入口补齐状态，幂等）。"""
    db = process_loop.AsyncSessionLocal()
    try:
        await db.execute(
            update(CloneScript)
            .where(CloneScript.id == clone_script_id)
            .values(
                clone_status=status,
                clone_progress=progress,
                clone_error_message=None,
            )
        )
        await db.commit()
    except Exception:
        logger.exception('set clone stage failed')
    finally:
        await db.close()

async def process_error(state:CloneState):
    if state['cur_step'] <= 2:
        await send_fail_status(state['clone_script_id'], state['error'], flow_type='clone')
    else:
        await send_fail_status(state['clone_script_id'], state['error'], flow_type='generate')

clone_graph_builder = StateGraph(CloneState)

clone_graph_builder.add_node('select_step', select_step)
clone_graph_builder.add_node('plot_generation', plot_generation)
clone_graph_builder.add_node('voice_generation', voice_generation)
clone_graph_builder.add_node('storyboard_generation', storyboard_generation)
clone_graph_builder.add_node('image_base_generation', image_base_generation)
clone_graph_builder.add_node('segment_frame_generation', segment_frame_generation)
clone_graph_builder.add_node('video_generation', video_generation)
clone_graph_builder.add_node('video_merge', video_merge)
clone_graph_builder.add_node("process_error", process_error)

clone_graph_builder.add_edge(START, 'select_step')
clone_graph_builder.add_conditional_edges(
    'select_step',
    should_select_next_step,
    ['plot_generation', 'voice_generation', 'storyboard_generation', 'image_base_generation', 'segment_frame_generation', 'video_generation', 'video_merge', END]
)
clone_graph_builder.add_conditional_edges(
    'plot_generation',
    should_continue,
    ['process_error', 'select_step', END]
)

clone_graph_builder.add_conditional_edges(
    'voice_generation',
    should_continue,
    ['process_error', 'select_step', END]
)

clone_graph_builder.add_conditional_edges(
    'storyboard_generation',
    should_continue,
    ['process_error', 'select_step', END]
)

clone_graph_builder.add_conditional_edges(
    'image_base_generation',
    should_continue,
    ['process_error', 'select_step', END]
)

clone_graph_builder.add_conditional_edges(
    'segment_frame_generation',
    should_continue,
    ['process_error', 'select_step', END]
)

clone_graph_builder.add_conditional_edges(
    'video_generation',
    should_continue,
    ['process_error', 'select_step', END]
)

clone_graph_builder.add_conditional_edges(
    'video_merge',
    should_continue,
    ['process_error', 'select_step', END]
)
clone_graph_builder.add_edge('process_error', END)

clone_graph = clone_graph_builder.compile(checkpointer=False)

async def begin_clone(clone_script_id: int, step: int=1, auto_run: bool=False, stop_step: int=8):
    try:
        initial_input = {
            "clone_script_id": clone_script_id,
            "error": "",
            "step": step,
            "auto_run": auto_run,
            "stop_step": stop_step,
            "cur_step": 1
        }
        await clone_graph.ainvoke(initial_input)
    except Exception as e:
        await send_fail_status(clone_script_id=clone_script_id, error=str(e))

from typing import TypedDict
from app.services.clone_plot import clone_plot_graph, send_fail_status
from app.services.clone_storyboard import clone_storyboard_graph
from langgraph.graph import END, START, StateGraph
from app.services.gen_voice import GenVoice
from celery.utils.log import get_task_logger
from app.services.clone_voice import CustomVoiceContext, clone_voice_graph
from app.services.clone_image import clone_image_graph

logger = get_task_logger(__name__)

class CloneState(TypedDict):
    clone_script_id: int # 复刻脚本id
    error: str
    step: int
    auto_run: bool  # 自动走流程


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
        return 'voice_generation'
    if step == 3:
        return 'storyboard_generation'
    if step == 4:
        return 'image_generation'
    if step == 5:
        return 'video_generation'
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
        return {'error': str(e)},

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
            'step': 3
        }
    except Exception as e:
        logger.info(f'catch error in storyboard_generation. {str(e)}')
        return {'error': str(e)},

async def storyboard_generation(state: CloneState):
    try:
        logger.info('begin run storyboard_generation')

        initial_input = {
            "clone_script_id": state["clone_script_id"],
            "storyboard_script": None,
            "plot_role_library": {},
            "plot_scene_library": {},
            "character_manifest": None,
            "error": "",
            "retry_cnt": 0,
            "retry_messages": ''
        }
        await clone_storyboard_graph.ainvoke(initial_input)
        return {
            'step': 4
        }
    except Exception as e:
        logger.info(f'catch error in storyboard_generation. {str(e)}')
        return {'error': str(e)}
    
async def image_generation(state: CloneState):
    try:
        logger.info('begin run storyboard_generation')

        input_data = {
            "clone_script_id": state["clone_script_id"],
            "character_manifest": None,
            "role_asset_library": {},
            "scene_asset_library": {},
            "retry_messages": "",
            "error": ""
        }

        await clone_image_graph.ainvoke(input_data)
        return {
            'step': 5
        }
    except Exception as e:
        logger.info(f'catch error in storyboard_generation. {str(e)}')
        return {'error': str(e)}
    
async def video_generation(state: CloneState):
    try:
        logger.info('begin run video_generation')
        return {
            'step': 6
        }

    except Exception as e:
        logger.info(f'catch error in video_generation. {str(e)}')
        return {'error': str(e)},

async def should_continue(state: CloneState):
    if state['error']:
        return 'process_error'
    if state['auto_run']:
        return 'select_step'
    return END

async def process_error(state:CloneState):
    await send_fail_status(state['clone_script_id'], state['error'])

clone_graph_builder = StateGraph(CloneState)

clone_graph_builder.add_node('select_step', select_step)
clone_graph_builder.add_node('plot_generation', plot_generation)
clone_graph_builder.add_node('voice_generation', voice_generation)
clone_graph_builder.add_node('storyboard_generation', storyboard_generation)
clone_graph_builder.add_node('image_generation', image_generation)
clone_graph_builder.add_node('video_generation', video_generation)
clone_graph_builder.add_node("process_error", process_error)

clone_graph_builder.add_edge(START, 'select_step')
clone_graph_builder.add_conditional_edges(
    'select_step',
    should_select_next_step,
    ['plot_generation', 'voice_generation', 'storyboard_generation', 'image_generation', 'video_generation', END]
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
    'image_generation',
    should_continue,
    ['process_error', 'select_step', END]
)

clone_graph_builder.add_conditional_edges(
    'video_generation',
    should_continue,
    ['process_error', 'select_step', END]
)
clone_graph_builder.add_edge('process_error', END)

clone_graph = clone_graph_builder.compile(checkpointer=False)

async def begin_clone(clone_script_id: int, step: int=1, auto_run: bool=False):
    try:
        initial_input = {
            "clone_script_id": clone_script_id,
            "error": "",
            "step": step,
            "auto_run": auto_run
        }
        await clone_graph.ainvoke(initial_input)
    except Exception as e:
        await send_fail_status(clone_script_id=clone_script_id, error=str(e))

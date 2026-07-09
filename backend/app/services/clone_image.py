

import inspect
import os
from pathlib import Path
from typing import Literal, TypedDict

from celery.utils.log import get_task_logger
from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command
from sqlalchemy import delete, select
from app.database import AsyncSessionLocal, SessionLocal
from app.models.script import CloneImage, CloneScript, CloneScriptSegment, CloneStatus, ScriptSegment
from app.services.clone_plot import send_fail_status
from app.services.gen_image import GenImage, GenImageParams, ImageSize
from app.services.llm import CharacterManifest, CloneAnalysis
from app.config import settings
from app.util import get_image_info, make_dir

logger = get_task_logger(__name__)


def log_node_start():
    # [1] 代表上一层调用者的堆栈帧
    caller_name = inspect.stack()[1].function
    logger.info(f"======== 🚀 LangGraph 节点开始执行: [{caller_name}] ========")

class CloneImageState(TypedDict):
    clone_script_id: int
    character_manifest: CharacterManifest | None # 人物生图提示词
    role_asset_library: dict # 角色资产信息列表
    scene_asset_library: dict # 场景资产信息列表
    retry_messages: str
    error: str


async def abstract_role_info(state: CloneImageState):
    from app.services.llm import PRODUCER_QUERY_PROMPT, PRODUCER_SYSTEM_PROMPT, producer_model
    log_node_start()
    db = AsyncSessionLocal()
    try:
        statment = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
        clone_script = statment.scalar_one_or_none()
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        await db.execute(delete(CloneImage).where(CloneImage.script_id == state['clone_script_id']))
        clone_script.clone_progress = 36
        await db.commit()

        parse_pointer = CloneAnalysis.model_validate_json(clone_script.clone_parse_pointer)


        statment = await db.execute(select(CloneScriptSegment).where(CloneScriptSegment.script_id==clone_script.id))
        storyboard = statment.scalars().all()

        storyboard_dict = [vars(segment) for segment in storyboard]
        logger.info(f'abstract_role_info get storyboard is {storyboard_dict}')
        

        role_asset_library = [role.model_dump() for role in parse_pointer.role_library]
        scene_asset_library = [scene.model_dump() for scene in parse_pointer.scene_library]

        logger.info(f'role_asset_library: {role_asset_library}')
        logger.info(f'scene_asset_library: {scene_asset_library}')

        # storyboard_json = storyboard.model_dump()
        query = PRODUCER_QUERY_PROMPT.format(
            role_library=role_asset_library,
            style_template=parse_pointer.global_style.model_dump(),
            storyboard=storyboard_dict,
            retry_messages=state['retry_messages']
        )
        messages = [SystemMessage(PRODUCER_SYSTEM_PROMPT),
                    HumanMessage(query)]
        response = await producer_model.ainvoke(
            messages,
            config={
                "configurable": {
                    "temperature":0.7
                }
            }
        )
        if not isinstance(response, CharacterManifest):
            raise Exception("abstract_role_info llm输出格式错误")

        logger.info(f'abstract_role_info output: {response.model_dump_json()}')

        return Command(
            update={
                'character_manifest': response,
                'role_asset_library': role_asset_library,
                'scene_asset_library': scene_asset_library
            },
            goto='check_role_info'
        )

    except Exception as e:
        error_message = f'generate_storyboard failed. {str(e)}'
        logger.info(error_message)
        logger.exception('abstract_role_info 生成任务详情出错')
        return Command(
            update={'error': error_message},
            goto="process_error"
        )
        # return {'error': f'generate_storyboard failed. {str(e)}'}
    finally:
        await db.close()

async def check_role_info(state: CloneImageState):
    log_node_start()
    try:
        plot_role_name = [role['role_name'] for role in state['role_asset_library'] if 'role_name' in role]
        character_manifest = state['character_manifest']
        logger.info(f'plot_role_name:{plot_role_name}')


        extra_role_messages = ''
        for character in character_manifest.character_list:
            if character.role_name not in plot_role_name:
                logger.info(f'find role_name:{character.role_name} not in plot_role_name')
                extra_role_messages += f'发现剧本中存在人物名({character.role_name}) 不在视频脚本中 \n'
        
        retry_messages=''
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
        logger.exception('check_role_info 发生错误')
        return {
            'retry_messages':error_message,
            'error': error_message,
            'retry_cnt': settings.STORYBOARD_TRY_COUNT + 1
        }

async def need_retry_abstract(state: CloneImageState):
    retry_max = settings.STORYBOARD_TRY_COUNT
    retry_cnt = state.get('retry_cnt', 0)
    if state['retry_messages']:
        if retry_cnt <= retry_max:
            return 'abstract_role_info'
        return 'process_error'
    return 'initial_role_images'

async def initial_role_images(state: CloneImageState) -> Command[Literal['initial_segment_images', 'process_error']]:
    """
    生成图片
    """
    log_node_start()
    db = AsyncSessionLocal()
    try:
        character_manifest = state['character_manifest']
        if not isinstance(character_manifest, CharacterManifest):
            raise Exception('character_manifest is None.')
        
        statment = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
        clone_script = statment.scalar_one_or_none()

        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        gen_image = GenImage()

        save_dir = settings.UPLOAD_DIR + '/clone_' + str(state['clone_script_id'])
        make_dir(save_dir, re_create=False)

        role_img_info = {}
        for character in character_manifest.character_list:
            if character.visual_anchor_prompt:
                params = GenImageParams(
                    prompt=character.visual_anchor_prompt,
                    image_size=ImageSize.SIZE_1024x1024.value
                )
                image_path_list = await gen_image.gen_image(gen_image_params=params, save_dir=save_dir, prefix=character.role_name)
                logger.info(f'get image path list: {image_path_list}')
                role_img_info[character.role_name] = image_path_list
                if not image_path_list:
                    raise Exception(f'not find this image. {image_path}')
                image_path = image_path_list[0]
                if not image_path.is_file():
                    raise Exception(f'not find this image. {image_path}')
                
                image_info = get_image_info(image_path)
                clone_image = CloneImage(
                    script_id=clone_script.id, 
                    role_name=character.role_name, 
                    width=image_info['width'],
                    height=image_info['height'],
                    path=str(image_path.absolute()),
                    desc='portrait'
                )
                db.add(clone_image)



        clone_script.clone_status = CloneStatus.IMAGE_DONE
        clone_script.clone_progress = 50
        await db.commit()
                    
        return Command(goto='initial_segment_images')
    except Exception as e:
        error_message = f'initial_role_images failed. {str(e)}'
        logger.exception('initial_role_images 发生错误')
        logger.info(error_message)

        return Command(
            update={'error': error_message},
            goto="process_error"
        )

async def three_view_drawing(state:CloneImageState):
    "图生图 通过人物肖像获取三视图"
    pass
    
async def initial_segment_images(state: CloneImageState):
    """ 获取分镜首帧 """
    log_node_start()
    return Command(goto='__end__')
    

async def process_error(state: CloneImageState):
    log_node_start()
    retry_max = settings.STORYBOARD_TRY_COUNT
    retry_cnt = state.get('retry_cnt', 0)
    if not state['error'] and retry_cnt > retry_max:
        await send_fail_status(state['clone_script_id'], '重试次数超过限制')
    else:
        await send_fail_status(state['clone_script_id'], state['error'])
    logger.info('process_error')



clone_image_builder = StateGraph(CloneImageState)

clone_image_builder.add_node('abstract_role_info', abstract_role_info)
clone_image_builder.add_node('check_role_info', check_role_info)
clone_image_builder.add_node('initial_role_images', initial_role_images)
clone_image_builder.add_node('initial_segment_images', initial_segment_images)

clone_image_builder.add_node('process_error', process_error)


clone_image_builder.add_edge(START, 'abstract_role_info')

clone_image_builder.add_conditional_edges(
    'check_role_info',
    need_retry_abstract,
    ['abstract_role_info', 'process_error', 'initial_role_images']
)

clone_image_builder.add_edge('process_error', END)

clone_image_graph = clone_image_builder.compile(checkpointer=False)
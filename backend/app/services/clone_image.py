

from contextvars import ContextVar
import inspect
import os
from pathlib import Path
import random
import threading
from typing import Literal, TypedDict

from celery.utils.log import get_task_logger
from langchain.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, RetryPolicy
from pydantic import BaseModel
from sqlalchemy import delete, select
from app.tasks.process_loop_manager import process_loop
from app.models.script import CloneImage, CloneRoleImage, CloneSceneImage, CloneScript, CloneScriptSegment, CloneSegmentImg, CloneStatus, GenerateStatus, ScriptSegment
from app.services.clone_plot import send_fail_status
from app.services.gen_image import GenImage, GenImageParams, ImageSize, ReferImageInfo
from app.services.llm import SCENE_GENERATE_PROMPT, CharacterManifest, CloneAnalysis, SceneManifest, SegmentRoleView, scene_generate_model
from app.config import settings
from app.util import ImageRegenerateInput, async_retry_error, get_image_info, make_dir
from sqlalchemy.ext.asyncio import AsyncSession

logger = get_task_logger(__name__)

# 声明一个 ContextVar 并指定默认值为空字符串 ''
generate_error_msg: ContextVar[str] = ContextVar('scene_prmpt_msg', default='')

def log_node_start():
    # [1] 代表上一层调用者的堆栈帧
    caller_name = inspect.stack()[1].function
    logger.info(f"======== 🚀 LangGraph 节点开始执行: [{caller_name}] ========")

class CloneImageState(TypedDict):
    clone_script_id: int
    character_manifest: CharacterManifest | None # 人物生图提示词
    role_asset_library: dict # 角色资产信息列表
    scene_manifest: SceneManifest | None # 场景生图提示词
    scene_asset_library: dict # 场景资产信息列表
    global_style: str # 全局画风母版
    retry_messages: str
    error: str


async def abstract_role_info(state: CloneImageState):
    from app.services.llm import PRODUCER_QUERY_PROMPT, PRODUCER_SYSTEM_PROMPT, producer_model
    log_node_start()
    db = process_loop.AsyncSessionLocal()
    try:
        statment = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
        clone_script = statment.scalar_one_or_none() # 查询条件必须是唯一，否则会报错
        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        # 先删除 role scene 已生成的数据
        await db.execute(delete(CloneRoleImage).where(CloneRoleImage.script_id == state['clone_script_id']))
        await db.execute(delete(CloneSceneImage).where(CloneSceneImage.script_id == state['clone_script_id']))
        clone_script.clone_progress = 36
        await db.commit()

        parse_pointer = CloneAnalysis.model_validate_json(clone_script.clone_parse_pointer)


        statment = await db.execute(select(CloneScriptSegment).where(CloneScriptSegment.script_id==clone_script.id))
        storyboard = statment.scalars().all()

        storyboard_dict = [segment.shot_description for segment in storyboard]
        logger.info(f'abstract_role_info get storyboard is {storyboard_dict}')
        

        role_asset_library = [role.model_dump() for role in parse_pointer.role_library]
        scene_asset_library = [scene.model_dump() for scene in parse_pointer.scene_library]

        logger.info(f'role_asset_library: {role_asset_library}')
        logger.info(f'scene_asset_library: {scene_asset_library}')

        # storyboard_json = storyboard.model_dump()
        query = PRODUCER_QUERY_PROMPT.format(
            role_library=role_asset_library,
            style_template=parse_pointer.global_style.global_style_suffix,
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
                'scene_asset_library': scene_asset_library,
                'global_style': parse_pointer.global_style.global_style_suffix,
            },
            goto='check_role_info'
        )

    except Exception as e:
        error_message = f'abstract_role_info failed. {str(e)}'
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
    return 'abstract_scene_info'


async def abstract_scene_info(state: CloneImageState):
    try:
        scene_library = state['scene_asset_library']
        global_style = state['global_style']
        
        plot_scene_name = [role['scene_name'] for role in state['scene_asset_library'] if 'scene_name' in role]
        logger.info(f'plot_scene_name:{plot_scene_name}')
        
        query = SCENE_GENERATE_PROMPT.format(
            scene_description=scene_library,
            visual_style=global_style,
            error_message=generate_error_msg.get()
        )
        response = await scene_generate_model.ainvoke(
            [HumanMessage(query)],
            config={
                "configurable": {
                    "temperature":0.7
                }
            })
        if not isinstance(response, SceneManifest):
            generate_error_msg.set('生成结果格式不正确')
            raise Exception('生成结果格式不正确')
        for scene_prompt in response.scene_prompt_list:
            if scene_prompt.scene_name not in plot_scene_name:
                generate_error_msg.set(f'生成场景名不在【场景清单】中')
                raise Exception(f'生成场景名：{scene_prompt.scene_name} 不在【场景清单】中')
        return Command(
            update={'scene_manifest': response},
            goto="initial_role_images"
        )
    except Exception as e:
        error_message = f'abstract_scene_info 失败 {str(e)}'
        logger.exception(error_message)
        return Command(
            update={'error': error_message},
            goto="process_error"
        )
        
async def generate_image(prompt: str, save_dir: str|Path, prefix:str,  img_type:Literal['role', 'scene', 'frame'], seed:int=None, refer_imgs: list[ReferImageInfo]=None) -> tuple[str|list, int]:
    params = GenImageParams(
        prompt=prompt,
        image_size=ImageSize.SIZE_1024x1024,
        seed=seed
    )
    if settings.USER_COMFY_IMAGE:
        match img_type:
            case 'role':
                params.image_size=ImageSize.SIZE_512x640
                image_path_list = await GenImage.t2i_local_flux2_klien(gen_image_params=params, save_dir=save_dir, prefix=prefix)
            case 'scene':
                params.image_size=ImageSize.SIZE_1280x720
                image_path_list = await GenImage.t2i_local_flux2_klien(gen_image_params=params, save_dir=save_dir, prefix=prefix)
            case 'frame':
                # 这里要根据目标宽高比设置，目前指定竖屏
                params.image_size=ImageSize.SIZE_720x1280
                params.refer_images = refer_imgs
                image_path_list = []
                image_path_list = await GenImage.i2i_local_flux2_klien(gen_image_params=params, save_dir=save_dir, prefix=prefix)
            case _:
                raise ValueError(f'not find the img_type {img_type}')
            
    else:
        gen_image = GenImage()
        image_path_list = await gen_image.gen_image(gen_image_params=params, save_dir=save_dir, prefix=prefix)
    logger.info(f'get image path list: {image_path_list}')

    if not image_path_list:
        raise Exception(f'not find this image. {image_path}')
    image_path = image_path_list[0]
    name_comfy = None
    if isinstance(image_path, list):
        name_comfy = image_path[0]
        image_path = image_path[1]
    
    if not image_path.is_file():
        raise Exception(f'not find this image. {image_path}')
    return name_comfy, image_path, params.seed
    


async def initial_role_images(state: CloneImageState) -> Command[Literal['initial_scene_images', 'process_error']]:
    """生成角色肖像图
    
    Args:
        state (CloneImageState): 上下文

    Raises:
        Exception: CharacterManifest资产不存在
        Exception: clone_script 脚本不存在
        Exception: 未生成角色肖像图
        Exception: 生成路径非文件

    Returns:
        Command: 去 生成场景图 节点
    """
    log_node_start()
    db = process_loop.AsyncSessionLocal()
    try:
        character_manifest = state['character_manifest']
        if not isinstance(character_manifest, CharacterManifest):
            raise Exception('character_manifest is None.')
        
        statment = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
        clone_script = statment.scalar_one_or_none()

        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        save_dir = settings.UPLOAD_DIR + '/clone_' + str(state['clone_script_id'])
        make_dir(save_dir, re_create=False)

        for character in character_manifest.character_list:
            if character.visual_anchor_prompt:
                name_comfy, image_path, seed = await generate_image(
                    prompt=character.visual_anchor_prompt, 
                    save_dir=save_dir, 
                    prefix=character.role_name,  
                    img_type='role'
                )
                image_info = get_image_info(image_path)
                clone_image = CloneRoleImage(
                    script_id=clone_script.id, 
                    role_name=character.role_name, 
                    width=image_info['width'],
                    height=image_info['height'],
                    path=str(image_path.absolute()),
                    desc='角色肖像',
                    prompt=character.visual_anchor_prompt,
                    faceless=character.faceless,
                    seed=seed,
                    status=GenerateStatus.SUCCESS,
                    version=0,
                    name_comfy=name_comfy
                )
                db.add(clone_image)

        clone_script.clone_progress = 40
        await db.commit()
                    
        return Command(goto='initial_scene_images')
    except Exception as e:
        error_message = f'initial_role_images failed. {str(e)}'
        logger.exception('initial_role_images 发生错误')
        logger.info(error_message)

        return Command(
            update={'error': error_message},
            goto="process_error"
        )
    finally:
        await db.close()
    
    
async def initial_scene_images(state: CloneImageState):
    """生成场景图

    Args:
        state (CloneImageState): 上下文

    Raises:
        Exception: 未生成复刻脚本

    Returns:
        Command: 跳转路径 动态边
    """
    log_node_start()
    db = process_loop.AsyncSessionLocal()
    try:
        scene_manifest = state['scene_manifest']
        if not isinstance(scene_manifest, SceneManifest):
            raise ValueError('scene_manifest type error')
        
        statment = await db.execute(select(CloneScript).where(CloneScript.id == state['clone_script_id']))
        clone_script = statment.scalar_one_or_none()

        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
        
        save_dir = settings.UPLOAD_DIR + '/clone_' + str(state['clone_script_id'])
        make_dir(save_dir, re_create=False)
        
        for scene_info in scene_manifest.scene_prompt_list:
            name_comfy, image_path, seed = await generate_image(
                prompt=scene_info.scene_prompt, 
                save_dir=save_dir, 
                prefix=scene_info.scene_name,  
                img_type='scene'
            )
            image_info = get_image_info(image_path)
            clone_image = CloneSceneImage(
                script_id=clone_script.id, 
                scene_name=scene_info.scene_name, 
                width=image_info['width'],
                height=image_info['height'],
                path=str(image_path.absolute()),
                desc='场景',
                seed=seed,
                prompt=scene_info.scene_prompt,
                status=GenerateStatus.SUCCESS,
                version=0,
                name_comfy=name_comfy
            )
            db.add(clone_image)
        clone_script.clone_progress = 45
        clone_script.clone_status = CloneStatus.IMAGE_DONE
        await db.commit()
        return Command(goto='__end__')
    except Exception as e:
        error_message = f'initial_role_images failed. {str(e)}'
        logger.exception('initial_role_images 发生错误')
        logger.info(error_message)

        return Command(
            update={'error': error_message},
            goto="process_error"
        )
    finally:
        await db.close()
    

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

# 配置等价于：重试 3 次，每次固定延迟 1.0 秒
my_retry_policy = RetryPolicy(
    max_attempts=3,       # 最大尝试次数（包含第 1 次执行，所以共重试 2 次。若要纯重试 3 次请设为 4）
    initial_interval=1.0, # 初始延迟 1.0 秒
    backoff_factor=1.0,   # 延迟不翻倍
    jitter=False          # 关闭随机抖动，确保每次都是精准的 1.0 秒
)

clone_image_builder.add_node('abstract_role_info', abstract_role_info)
clone_image_builder.add_node('check_role_info', check_role_info)
clone_image_builder.add_node('abstract_scene_info', abstract_scene_info, retry_policy=my_retry_policy)
clone_image_builder.add_node('initial_role_images', initial_role_images)
clone_image_builder.add_node('initial_scene_images', initial_scene_images)

clone_image_builder.add_node('process_error', process_error)

clone_image_builder.add_edge(START, 'abstract_role_info')

clone_image_builder.add_conditional_edges(
    'check_role_info',
    need_retry_abstract,
    ['abstract_role_info', 'process_error', 'abstract_scene_info']
)

clone_image_builder.add_edge('process_error', END)

clone_image_graph = clone_image_builder.compile(checkpointer=False)



async def get_image_data(db: AsyncSession, detail_category: Literal['role', 'scene', 'frame'], id: int) -> CloneImage|None:
    if 'role' == detail_category:
        res = await db.execute(select(CloneRoleImage).where(CloneRoleImage.id == id))
        return res.scalar_one()
    elif 'scene' == detail_category:
        res = await db.execute(select(CloneSceneImage).where(CloneSceneImage.id == id))
        return res.scalar_one()
    elif 'frame' == detail_category:
        res = await db.execute(select(CloneSegmentImg).where(CloneSegmentImg.id == id))
        return res.scalar_one()
    return None
    

async def regenerate_image(detail_category: Literal['role', 'scene'], id: int, payload_dict: dict):
    db = process_loop.AsyncSessionLocal()
    try:
        image_element = await get_image_data(db, detail_category, id)
        if not image_element:
            raise ValueError(f'could not find the element with id={id} in {detail_category}')
        
        logger.info(f'payload_dict is {payload_dict}')
        payload = ImageRegenerateInput.model_validate(payload_dict)
        
        payload.width = payload.width if payload.width else image_element.width
        payload.height = payload.height if payload.height else image_element.height
        payload.seed = payload.seed if payload.seed else image_element.seed
        
        abs_path = Path(image_element.path)
        save_dir = abs_path.parent
        prefix = abs_path.stem.rsplit('_', 1)[0]
        logger.info(f'regenerate image. save_dir:{save_dir}, prefix:{prefix}')
        
        name_comfy, image_path, seed = await generate_image(
            prompt=payload.prompt, 
            save_dir=save_dir, 
            prefix=prefix,  
            img_type=detail_category
        )
        
        logger.info(f'image path is {str(image_path.absolute())}')
        image_info = get_image_info(image_path)
        image_element.prompt = payload.prompt
        image_element.width = image_info['width']
        image_element.height = image_info['height']
        image_element.path = str(image_path.absolute())
        image_element.seed = seed
        image_element.status = GenerateStatus.SUCCESS
        image_element.version += 1
        image_element.name_comfy = name_comfy
        
        await db.commit()
    except ValueError:
        logger.exception('regenerate_image 发生错误, 未找到数据')
        raise
    except Exception as e:
        logger.exception('regenerate_image 发生错误')
        await db.rollback()  # ✅ 先回滚，重置数据库 Session 状态
        if image_element:
            image_element.status = GenerateStatus.FAILED
            await db.commit()
        raise
    finally:
        await db.close()
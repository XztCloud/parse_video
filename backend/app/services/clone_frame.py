import inspect
from pathlib import Path
import random
import uuid

from celery.utils.log import get_task_logger
from openai import BaseModel
import requests
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.script import CloneRoleImage, CloneSceneImage, CloneScript, CloneScriptSegment, CloneSegmentImg, CloneStatus, GenerateStatus
from app.services.llm import SegmentRoleView
from app.tasks.process_loop_manager import process_loop
from app.config import settings
from app.util import ImageRegenerateInput, get_image_info, make_dir
from app.services.gen_image import ReferImageInfo
from app.services.clone_image import generate_image

logger = get_task_logger(__name__)

BEGIN_PROGRESS = 46 
COMPLETE_PROGRESS = 60

def log_node_start():
    # [1] 代表上一层调用者的堆栈帧
    caller_name = inspect.stack()[1].function
    logger.info(f"======== 🚀 LangGraph 节点开始执行: [{caller_name}] ========")
    
class FilterSceneInfo(BaseModel):
    scene_name: str
    prompt: str
    path: str
    
async def filter_scene_info(db: AsyncSession, scene_name: str, clone_script_id: int) -> FilterSceneInfo:
    """根据scene_name筛选场景提示词 和 场景图片在comfy中名称

    Args:
        db (AsyncSession): 数据库
        scene_name (str): 场景名
        clone_script_id (str): 复刻脚本id
    
    Returns:
        str: 场景提示词
        str: 本地图片路径
    """
    res = await db.execute(select(CloneSceneImage).where(CloneSceneImage.script_id==clone_script_id,CloneSceneImage.scene_name==scene_name))
    scene_image = res.scalar_one_or_none()
    if not scene_image:
        raise Exception(f'not find this scene image {scene_name}')
    if not scene_image.prompt or not scene_image.name_comfy:
        raise Exception(f'not find prompt or name_comfy in the scene image {scene_name}')
    return FilterSceneInfo(scene_name=scene_name, prompt=scene_image.prompt, path=scene_image.path)
    
class FilterRoleInfo(BaseModel):
    # 人物提示词 位置 动作 表情 和 人物图片在comfy中名称
    role_name: str
    position: str
    action: str
    emotion: str
    prompt: str
    faceless: str # 全身定妆描述词
    path: str
    
async def filter_role_info(db: AsyncSession, segment: CloneScriptSegment, clone_script_id: int) -> list[FilterRoleInfo]:
    """获取分镜中出境人物信息

    Args:
        db (AsyncSession): 数据库
        role_name (str): 角色名
        clone_script_id (str): 复刻脚本id
        
    Returns:
        list[FilterRoleInfo]: 角色信息
    """
    role_view_info = segment.role_view_info
    if not role_view_info:
        logger.info(f'{segment.start_time} - {segment.end_time} no role visible')
        return None
    result = []
    for role_view in role_view_info:
        segment_role_view = SegmentRoleView.model_validate(role_view)
        if segment_role_view.visibility == 'offscreen':
            logger.info(f'{segment_role_view.role_name} in this segement offscreen')
            continue
        role_name =segment_role_view.role_name
    
        res = await db.execute(select(CloneRoleImage).where(CloneRoleImage.script_id == clone_script_id, CloneRoleImage.role_name == role_name))
        role_image = res.scalar_one_or_none()
        if not role_image:
            raise Exception(f'not find this role image {role_image}')
        if not role_image.prompt or not role_image.name_comfy:
            raise Exception(f'not find prompt or name_comfy in the role image {role_image}')
        filter_role_info = FilterRoleInfo(
            role_name=role_name,
            position=segment_role_view.position,
            action=segment_role_view.action,
            emotion=segment_role_view.emotion,
            prompt=role_image.prompt,
            faceless=role_image.faceless,
            path=role_image.path
        )
        result.append(filter_role_info)
    return result
        
async def merge_frame_prompt(scene_info: FilterSceneInfo, role_info_list: list[FilterRoleInfo], refer_img_list: list[ReferImageInfo], shot: str) -> str:
    """根据筛选信息合并成图生图提示词

    Args:
        scene_info (FilterSceneInfo): 分镜所在场景
        role_info_list (list[FilterRoleInfo]): 分镜角色列表

    Returns:
        str: 分镜首帧生图提示词
    """
    merge_prompt = """
生成一张电影级影视分镜首帧图片。
参考图片说明：

"""
    pic_role_statement = ''
    pic_role_detail = ''
    for i, role_info in enumerate(role_info_list):
        refer_img_list.append(ReferImageInfo(type='role', path=role_info.path))
        pic_role_statement += f'第{i+1}张人物参考图用于保持{role_info.role_name}身份。 \n'
        
# {'23岁女性，身形娇小，蓄着一头及腰的栗色微卷长发，发丝蓬松。身上穿着一件宽松慵懒的松石绿粗针厚毛衣，下搭一条干净的白色直筒牛仔裤。脚上穿着一双复古风的双色拼接帆布鞋。整体装束舒适随性，充满居家或午后出游的温柔活力。' if i ==0 else '25岁女性，身材高挑纤细，留着一头利落的深棕色齐肩锁骨短发。全身穿着一件版型硬挺的米色双排扣中长款风衣，里面叠穿黑色高领针织衫。下身是修身的深色西装裤，脚踩一双黑色细跟皮质踝靴。整体散发着职场轻熟女的知性与干练气质。'}

        pic_role_detail += f"""
        
【镜头】
{shot}

【角色{i+1}】
名称：{role_info.role_name}

肖像：
参考图片{i+1}中的人物脸部特征。

外貌：
{role_info.faceless}

位置：
{role_info.position}

动作：
{role_info.action}

情绪：
{role_info.emotion}

"""
    refer_img_list.append(ReferImageInfo(type='scene', path=scene_info.path))
    pic_scene_statement = f'第{len(role_info_list) + 1}张图用于保持{scene_info.scene_name}场景环境'
    pic_scene_detail = f"""
【环境】
{scene_info.prompt}
保持参考场景的空间布局、位置和环境氛围。
"""
    return merge_prompt + pic_role_statement + pic_scene_statement + pic_role_detail + pic_scene_detail
        
    
async def upload_img_to_comfy(refer_img_list: list[ReferImageInfo]):
    url = settings.COMFY_URL + '/upload/image'
    for image_path in refer_img_list:
        with open(image_path.path, "rb") as f:
            # files 字典的 key 必须是 'image'
            files = {"image": f}
            # 如果需要，可以通过 overwrite 覆盖同名文件
            data = {"overwrite": "true"}
            response = requests.post(url, files=files, data=data)

        if response.status_code == 200:
            result = response.json()
            image_path.name_comfy = result["name"]  # 返回服务器上的文件名（例如: "example.png"）
            logger.info(f'send comfy name is {image_path.name_comfy}')
        else:
            raise Exception(f"图片上传失败: {response.text}")


async def regenerate_segment_frame(clone_seg_img_id: int, payload_dict: dict):
    db = process_loop.AsyncSessionLocal()
    try:
        # 找分镜图片
        res = await db.execute(select(CloneSegmentImg).where(CloneSegmentImg.id == clone_seg_img_id))
        clone_seg_img = res.scalar_one_or_none()
        if not clone_seg_img:
            raise Exception(f'not find CloneSegmentImg')
        
        # 通过分镜帧找到分镜信息
        res = await db.execute(select(CloneScriptSegment).where(CloneScriptSegment.id == clone_seg_img.clone_script_sgement_id))
        clone_segment = res.scalar_one_or_none()
        if not clone_segment:
            raise Exception(f'not find CloneSegment')
        
        ori_img_path = Path(clone_seg_img.path)
        logger.info(f'payload_dict is {payload_dict}')
        payload = ImageRegenerateInput.model_validate(payload_dict)
        
        payload.width = payload.width if payload.width else clone_seg_img.width
        payload.height = payload.height if payload.height else clone_seg_img.height
        payload.seed = payload.seed if payload.seed else clone_seg_img.seed
        
        abs_path = Path(clone_seg_img.path)
        save_dir = abs_path.parent
        prefix = abs_path.stem.rsplit('_', 1)[0]
        logger.info(f'regenerate image. save_dir:{save_dir}, prefix:{prefix}')
        
        refer_img_list: list[ReferImageInfo] = []
        refer_img_list.append(ReferImageInfo(type='scene', path=clone_seg_img.path))
        
        role_view_info = clone_segment.role_view_info

        for role_view in role_view_info:
            segment_role_view = SegmentRoleView.model_validate(role_view)
            if segment_role_view.visibility == 'offscreen':
                logger.info(f'{segment_role_view.role_name} in this segement offscreen')
                continue
            role_name =segment_role_view.role_name
        
            res = await db.execute(select(CloneRoleImage).where(CloneRoleImage.script_id == clone_segment.script_id, CloneRoleImage.role_name == role_name))
            role_image = res.scalar_one_or_none()
            if not role_image:
                raise Exception(f'not find this role image {role_image}')
            refer_img_list.append(ReferImageInfo(type='role', path=role_image.path))
        
        # 上传图片到comfy
        await upload_img_to_comfy(refer_img_list=refer_img_list)
        logger.info(f'regenerate frame refer_img_list:{refer_img_list}')
        
        prefix = f'segment_' + str(uuid.uuid4())
        logger.info(f'prefix: {prefix}')
        # 目前seed每次自动生成，不适用前端seed
        name_comfy, image_path, seed = await generate_image(
            prompt=payload.prompt, 
            save_dir=save_dir, 
            prefix=prefix,  
            img_type='frame',
            refer_imgs=refer_img_list
        )
        image_info = get_image_info(image_path)
        clone_seg_img.prompt = payload.prompt
        clone_seg_img.width=image_info['width']
        clone_seg_img.height=image_info['height']
        clone_seg_img.path=str(image_path.absolute())
        clone_seg_img.seed=seed
        clone_seg_img.status = GenerateStatus.SUCCESS
        clone_seg_img.version += 1
        clone_seg_img.name_comfy = name_comfy
        
        await db.commit()
        
        # 删除旧图片
        if ori_img_path.is_file():
            ori_img_path.unlink()
    except ValueError:
        logger.exception('regenerate_image 发生错误, 未找到数据')
        raise
    except Exception as e:
        logger.exception('regenerate_image 发生错误')
        await db.rollback()  # ✅ 先回滚，重置数据库 Session 状态
        if clone_seg_img:
            clone_seg_img.status = GenerateStatus.FAILED
            await db.commit()
        raise
    finally:
        await db.close()

async def generate_segment_frame_prompt(clone_script_id: int, go_head: bool=True):
    """生成分镜帧提示词，目前只生成首帧

    Args:
        state (CloneImageState): graph 上下文
        got_head (bool): True:保留上次已经生成完成的分镜，从未生成分镜帧的片段开始继续生成。 False:全部分镜重新生成

    Returns:
        Command: next 节点
    """
    log_node_start()
    db = process_loop.AsyncSessionLocal()
    try:
        statment = await db.execute(select(CloneScript).where(CloneScript.id ==clone_script_id))
        clone_script = statment.scalar_one_or_none()

        if not clone_script or not clone_script.clone_parse_pointer:
            raise Exception('not find clone_script in generate_storyboard')
            
        clone_script.clone_progress = BEGIN_PROGRESS
        await db.commit()
                
        res = await db.execute(select(CloneScriptSegment).where(CloneScriptSegment.script_id == clone_script_id).order_by(CloneScriptSegment.start_time))
        segments = res.scalars().all()
        
        save_dir = settings.UPLOAD_DIR + '/clone_' + str(clone_script_id)
        make_dir(save_dir, re_create=False)
        
        # test_cnt = 0
        for i, segment in enumerate(segments):
            logger.info(f'generate segment sequence: {i+1}/{len(segments)}, segment id: {segment.id}')
            if go_head:
                # 找分镜图片, 找到已生成则跳过
                res = await db.execute(select(CloneSegmentImg).where(CloneSegmentImg.clone_script_sgement_id == segment.id))
                # 如果增加多个参考帧，这里需要变化
                clone_seg_imgs = res.scalars().all()
                logger.info(f'clone_seg_imgs1: {clone_seg_imgs}')
                if clone_seg_imgs:
                    logger.info(f'clone_seg_imgs2: {clone_seg_imgs}')
                    _continue = True
                    for clone_seg_img in clone_seg_imgs:
                        logger.info(f'clone_seg_img status: {clone_seg_img.status}')
                        if clone_seg_img.status != GenerateStatus.SUCCESS:
                            logger.info('find status != SUCCESS, start regenerate it.')
                            _continue = False
                            # 失败的帧都先删除掉
                            await db.execute(delete(CloneSegmentImg).where(CloneSegmentImg.id == clone_seg_img.id))
                            await db.commit()
                    if _continue:
                        continue
            else:
                await db.execute(delete(CloneSegmentImg).where(CloneSegmentImg.clone_script_sgement_id == segment.id))
                await db.commit()
            # if test_cnt > 0:
            #     continue
            # test_cnt += 1
            refer_img_list = []
            logger.info(f'segment: {vars(segment)}')
            # 1. 根据据scene_name 找到 场景提示词 和 场景图片在comfy中名称
            scene_info = await filter_scene_info(db, segment.scene_name, clone_script_id)
            logger.info(f'scene_info: {scene_info}')
            # 2. 筛选role_view_info中可见角色信息，提取人物提示词 位置 动作 表情 和 人物图片在comfy中名称
            role_info_list = await filter_role_info(db, segment, clone_script_id)
            logger.info(f'role_info_list: {role_info_list}')
            if role_info_list is None:
                # 场景没有人物
                seed= random.randint(100000000000000, 999999999999999)
                image_path = Path(scene_info.path)
                image_info = get_image_info(image_path)
                clone_image = CloneSegmentImg(
                    clone_script_sgement_id=segment.id, 
                    width=image_info['width'],
                    height=image_info['height'],
                    path=str(image_path.absolute()),
                    desc=f'分镜{i+1} 首帧',
                    seed=seed,
                    prompt=scene_info.prompt,
                    status=GenerateStatus.SUCCESS,
                    version=0
                )
                db.add(clone_image)
                clone_script.clone_progress = BEGIN_PROGRESS + int((COMPLETE_PROGRESS - BEGIN_PROGRESS) * (i + 1) / len(segments))
                await db.commit()
                await db.refresh(clone_image)
                continue
            # continue
            # 3. 整合提取的场景信息 + 角色信息 + 分镜提示词 + 分镜镜头描述 + 分镜气氛 整合成提示词
            merge_prompt = await merge_frame_prompt(scene_info=scene_info, role_info_list=role_info_list, refer_img_list=refer_img_list, shot=segment.shot_type)
            logger.info(f'merge_prompt: {merge_prompt}')
            logger.info(f'refer_img_list: {refer_img_list}')
            
            # 4. 上传图片到comfy
            await upload_img_to_comfy(refer_img_list=refer_img_list)
            logger.info(f'after send comfy. refer_img_list is {refer_img_list}')
            
            
            # 5. 使用comfy流水线，输入提示词 角色图片 场景图片 输出分镜首帧
            prefix = f'segment_' + str(uuid.uuid4())
            logger.info(f'prefix: {prefix}')
            name_comfy, image_path, seed = await generate_image(
                prompt=merge_prompt, 
                save_dir=save_dir, 
                prefix=prefix,  
                img_type='frame',
                refer_imgs=refer_img_list
            )
            image_info = get_image_info(image_path)
            clone_image = CloneSegmentImg(
                clone_script_sgement_id=segment.id, 
                width=image_info['width'],
                height=image_info['height'],
                path=str(image_path.absolute()),
                desc=f'分镜{i+1} 首帧',
                seed=seed,
                prompt=merge_prompt,
                status=GenerateStatus.SUCCESS,
                version=0,
                name_comfy=name_comfy
            )
            db.add(clone_image)
            cur_progress = BEGIN_PROGRESS + int((COMPLETE_PROGRESS - BEGIN_PROGRESS) * (i + 1) / len(segments))
            logger.info(f'cur_progress: {cur_progress}')
            clone_script.clone_progress = cur_progress
            await db.commit()
            await db.refresh(clone_image)
        
            # 5. 保存数据库
        clone_script.clone_progress = COMPLETE_PROGRESS
        clone_script.clone_status = CloneStatus.FRAME_DONE
        await db.commit()
    except Exception as e:
        error_message = f'generate_segment_frame_prompt failed. {str(e)}'
        logger.info(error_message)
        logger.exception('generate_segment_frame_prompt 生成任务详情出错')
        # return Command(
        #     update={'error': error_message},
        #     goto="process_error"
        # )
        raise
    finally:
        await db.close()
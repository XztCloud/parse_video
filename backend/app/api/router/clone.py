

import os
from pathlib import Path as FilePath
from typing import Literal, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from app.database import SessionLocal
from app.models.script import CloneRoleImage, CloneSceneImage, CloneSegmentImg, CloneSegmentVideo, CloneVoice, CloneScript, CloneScriptSegment, CloneVideo, GenerateStatus, Script, CloneStatus
from app.tasks.parse_video import clone_video_task, regenerate_task
from app.util import REGENERATE_TYPE, ImageRegenerateInput, ImageRegenerateResponse, logger
from app.api.deps import AsyncSessionDep, SessionDep
from app.api.deps import limiter


class ClonePlotRequest(BaseModel):
    # 允许通过原名或别名进行赋值/解析
    model_config = {
        "populate_by_name": True  
    }
    video_id: int =  Field(..., alias="videoId")
    clone_theme: str =  Field(..., alias="cloneTheme")
    auto_run: bool = Field(default=False, alias="autoRun", description="自动进入下一阶段")
    style: Optional[str] = Field(default=None, description="视频风格 不填保持不变")
    product: Optional[str] = Field(default=None,description="带货商品 可以不填")
    product_desc: Optional[str] = Field(alias="productDesc", default=None, description="商品介绍")

class CloneRequestBase(BaseModel):
    # 允许通过原名或别名进行赋值/解析
    model_config = {
        "populate_by_name": True  
    }
    clone_script_id: int = Field(..., alias="cloneScriptId")
    auto_run: bool = Field(default=False,  alias="autoRun", description="自动进入下一阶段")

class ReClonePlotRequest(CloneRequestBase):
    pass

class CloneVoiceRequest(CloneRequestBase):
    pass

class CloneStoryboardRequest(CloneRequestBase):
    pass

class CloneImageRequest(CloneRequestBase):
    pass

router = APIRouter(prefix="/clone", tags=["clone"])


@router.post("/plot")
@limiter.limit("1/5second")
async def clone_plot(request: Request, request_data: ClonePlotRequest, db: SessionDep):
    try:
        logger.info(f'receive clone_plot post. auto run is {request_data.auto_run}')
        script = db.query(Script).filter(Script.video_id == request_data.video_id).first()
        if not script:
            raise HTTPException(status_code=404, detail="原视频脚本不存在")
        
        full_data = request_data.model_dump(exclude_none=True, by_alias=False)

        target_keys = {"style", "product", "product_desc"}
        filtered_dict = {k: v for k, v in full_data.items() if k in target_keys}
        clone_requirements = filtered_dict if filtered_dict is not None else None
        kwags = {
            "script_id": script.id,
            "clone_theme": request_data.clone_theme,
            "clone_status": CloneStatus.PLOT.value,
            "clone_progress": 0
        }
        if clone_requirements is not None:
            kwags["clone_requirements"] = clone_requirements

        clone_script = CloneScript(**kwags)
        
        db.add(clone_script)
        db.commit()
        db.refresh(clone_script)

        clone_video_task.delay(clone_script.id, 1, request_data.auto_run)
        return {"id": clone_script.id, "theme": request_data.clone_theme, "status": clone_script.clone_status, "progress": clone_script.clone_progress}
    except Exception:
        logger.error(f"复刻失败")
        raise

@router.post("/re_plot")
async def re_clone_plot(request: ReClonePlotRequest, db: SessionDep):
    try:
        logger.info(f'receive clone_plot post. auto run is {request.auto_run}')
        # 乐观锁  对比 .with_for_update().first() 悲观锁
        affected_rows = db.query(CloneScript).filter( 
            CloneScript.id == request.clone_script_id, 
            CloneScript.clone_status == CloneStatus.PLOT_DONE
            ).update({
                "clone_status": CloneStatus.PLOT,
                "clone_progress": 0,
                "clone_error_message": None,
                "clone_parse_pointer": None,
                "clone_parse_file_path": None
            })
        db.commit()
        if affected_rows == 0:
            raise HTTPException(status_code=404, detail="复刻任务已在运行或状态不正确")
        
        clone_script = db.query(CloneScript).filter(
            CloneScript.id == request.clone_script_id
        ).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        clone_video_task.delay(clone_script.id, 1, request.auto_run)
        return {"id": clone_script.id, "theme": request.clone_theme, "status": clone_script.clone_status, "progress": clone_script.clone_progress}
    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")

@router.get("/{clone_script_id}/status")
async def get_clone_status(clone_script_id: int, db: SessionDep):
    try:
        # logger.debug(f'receive get_clone_status. sciript_id is {clone_script_id}')

        clone_script = db.query(CloneScript).filter(CloneScript.id == clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在")
        return {
            "id": clone_script.id,
            "clone_status": (clone_script.clone_status.value 
                                if clone_script.clone_status 
                                else CloneStatus.PENDING.value),
            "clone_progress": (clone_script.clone_progress
                                if clone_script.clone_progress
                                else 0),
            "error_message": clone_script.clone_error_message
        }

    except Exception as e:
        print(f"获取状态失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取状态失败: {str(e)}")

@router.get("/{script_id}/list_clone_scripts")
async def list_clone_scripts(script_id: int, db: SessionDep, offset:int=0, limit:int=20):
    try:
        print(f'receive list_clone_scripts. sciript_id is {script_id}')
        clone_scripts = db.query(CloneScript).filter(CloneScript.script_id == script_id).order_by(CloneScript.updated_at.desc()).offset(offset).limit(limit).all()
        return [
            {
                "id": clone_scirpt.id,
                "clone_theme": clone_scirpt.clone_theme,
                "clone_status": (clone_scirpt.clone_status.value 
                                if clone_scirpt.clone_status 
                                else CloneStatus.PENDING.value),
                "clone_progress": clone_scirpt.clone_progress,
                "error_message": clone_scirpt.clone_error_message
            }
            for clone_scirpt in clone_scripts
        ]

    except Exception as e:
        print(f"获取复刻脚本列表失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取复刻脚本列表失败: {str(e)}")


@router.get("/{clone_script_id}")
async def get_clone_scirpt(clone_script_id: int, db: SessionDep):
    try:
        print(f'receive get_clone_scirpt. clone_scirpt_id is {clone_script_id}')
        clone_script = db.query(CloneScript).filter(CloneScript.id == clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在")
        print(f'clone_script status: {clone_script.clone_status}, progress: {clone_script.clone_progress}')
        plot_complete_status = list(CloneStatus)[2:-1]

        clone_script_content = ""
        voices = []
        segments = []
        images = []
        frames: list[CloneSegmentImg] = []
        segment_videos: list[CloneSegmentVideo] = []
        video: dict|None = None

        if clone_script.clone_status in plot_complete_status or \
            (clone_script.clone_status == CloneStatus.FAILED and clone_script.clone_progress >= 20):
            clone_parse_file_path = clone_script.clone_parse_file_path
            if clone_parse_file_path is None:
                raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
            clone_parse_file = FilePath(clone_parse_file_path)
            print(f'clone_parse_file_path: {clone_parse_file_path}')
            if clone_parse_file.is_file():
                with open(clone_parse_file_path, 'r', encoding='utf-8') as f:
                    clone_script_content = f.read()
                print(f'read plot script: {clone_script_content[:50]}')
                # 正确：使用 CloneVoice 自己的创建时间排序
                voices = db.query(CloneVoice).filter(CloneVoice.script_id == clone_script.id).order_by(CloneVoice.sort_order).all()
                segments = db.query(CloneScriptSegment).filter(CloneScriptSegment.script_id == clone_script.id).order_by(CloneScriptSegment.start_time).all()
                role_images = db.query(CloneRoleImage).filter(CloneRoleImage.script_id == clone_script.id).order_by(CloneRoleImage.created_at).all()
                scene_images = db.query(CloneSceneImage).filter(CloneSceneImage.script_id == clone_script.id).order_by(CloneSceneImage.created_at).all()
                
                for segment in segments:
                    segment_images = db.query(CloneSegmentImg).filter(CloneSegmentImg.clone_script_sgement_id == segment.id).order_by(CloneSegmentImg.created_at).all()
                    if segment_images:
                        frames.extend(segment_images)
                    segment_video = db.query(CloneSegmentVideo).filter(CloneSegmentVideo.clone_script_sgement_id == segment.id).first()
                    if segment_video:
                        segment_videos.append(segment_video)
                
                images = [{"id": img.id, "name": img.role_name, "width": img.width, "height": img.height, "desc": img.desc, "prompt": img.prompt, "seed": str(img.seed) if img.seed else None, "category":"role", 'status': img.status.value, 'version': img.version } for img in role_images]
                images += [{"id": img.id, "name": img.scene_name, "width": img.width, "height": img.height, "desc": img.desc, "prompt": img.prompt, "seed": str(img.seed) if img.seed else None, "category":"scene", 'status': img.status.value, 'version': img.version } for img in scene_images]
                
                video_data = db.query(CloneVideo).filter(CloneVideo.video_id == clone_script.id).first()
                if video_data:
                    video = {
                        "id": video_data.id,
                        "category": "video",
                        "duration": video_data.duration,
                    }
                # logger.info(f'images is {images}')
            else:
                raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
        
        
        return {
            "id": clone_script_id,
            "content": clone_script_content,
            "voices": [
                {
                    "id": voice.id,
                    "role_name": voice.role_name,
                    "duration": round(voice.duration,2),
                    "voice_type": voice.voice_type,
                    "spk_id": voice.spk_id,
                    "text": voice.text,
                }
                for voice in voices
            ],
            "segments": [
                {
                    "id": seg.id,
                    "start_time": seg.start_time,
                    "end_time": seg.end_time,
                    "shot_description": seg.shot_description,
                    "dialogue": [
                        {
                            "speaker": lines['role_name'],
                            "text": '(' + lines['lines_flag'] + ')'+lines['lines']
                        }
                        for lines in seg.dialogue
                    ],
                    "segment_type": seg.segment_type,
                }
                for seg in segments
            ],
            "images": [
                {
                    "id": img['id'],
                    "name": img['name'],
                    "width": img['width'],
                    "height": img['height'],
                    "desc": img['desc'],
                    "prompt": img['prompt'],
                    "seed": img['seed'],
                    "category": img['category'],
                    'status': img['status'],
                    'version': img['version'],
                }
                for img in images
            ],
            "frames": [
                {
                    "id": frame.id,
                    "name": f"分镜{i+1} 首帧",
                    "width": frame.width,
                    "height": frame.height,
                    "desc": frame.desc,
                    "prompt": frame.prompt,
                    "seed": frame.seed,
                    "category": 'frame',
                    'status': frame.status,
                    'version': frame.version,
                }
                for i, frame in enumerate(frames)
            ],
            "segment_videos": [
                {
                    "id": seg_v.id,
                    "name": f'分镜{i+1} 视频',
                    "width": seg_v.width,
                    "height": seg_v.height,
                    "desc": seg_v.desc,
                    "prompt": seg_v.prompt,
                    "seed": seg_v.seed,
                    "category": 'segment_video',
                    'status': seg_v.status,
                    'version': seg_v.version,
                    
                }
                for i, seg_v in enumerate(segment_videos)
            ],
            "video": video
        }

    except Exception as e:
        logger.exception('error')
        print(f"获取复刻脚本信息失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取复刻脚本信息失败: {str(e)}")


@router.get("/voice/{voice_id}")
async def export_voice(voice_id: str, db: SessionDep):
    """
    传入 voice id，返回音频文件流（前端可通过 Blob 接收）
    """
    try:
        logger.info(f'receive get voice, id:{voice_id}')
        clone_voice = db.query(CloneVoice).filter(CloneVoice.id == voice_id).first()
        path = FilePath(clone_voice.path)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="音频文件未找到")
        
        
        # 2. 检查是否为 MP3 文件
        if not clone_voice.path.lower().endswith('.mp3'):
            raise HTTPException(status_code=400, detail="只支持 MP3 格式的文件")
        return FileResponse(
            path=path, 
            media_type="audio/mpeg", 
            filename=os.path.basename(path)
        )

    except Exception as e:
        logger.error(f"获取复刻脚本信息失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取音频失败: {str(e)}")
    

@router.get("/{clone_script_id}/export/plot")
async def export_clone_script(clone_script_id: int, db: SessionDep):
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在")
        plot_complete_status = list(CloneStatus)[2:]
        if clone_script.clone_status not in plot_complete_status:
            raise HTTPException(status_code=400, detail=f"脚本复刻未完成，待完成后下载")

        clone_parse_file_path = clone_script.clone_parse_file_path
        if clone_parse_file_path is None:
            raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
        clone_parse_file = FilePath(clone_parse_file_path)
        print(f'clone_parse_file_path: {clone_parse_file_path}')
        if clone_parse_file.is_file():
            return FileResponse(
                path=clone_parse_file_path,
                filename=f"clone_{clone_script_id}.md",
                media_type="text/markdown" )
        else:
            raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
        
    except HTTPException:
        # 如果是主动抛出的 HTTPException，直接继续往外抛，不拦截、不拼接
        raise 
    except Exception as e:
        print(f"导出复刻脚本信息失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"导出复刻脚本信息失败: {str(e)}")

@router.get("/image/{category}/{image_id}")
async def export_image(
    db: SessionDep,
    category: Literal['role', 'scene', 'frame'] = Path(..., description="图片分类 (src)"), 
    image_id: int = Path(..., description="图片ID")
):
    logger.info(f'receive get image, category:{category}, id:{image_id}')
    try:
        match category:
            case 'role':
                clone_image = db.query(CloneRoleImage).filter(CloneRoleImage.id == image_id).first()
            case 'scene':
                clone_image = db.query(CloneSceneImage).filter(CloneSceneImage.id == image_id).first()
            case 'frame':
                clone_image = db.query(CloneSegmentImg).filter(CloneSegmentImg.id == image_id).first()
            case _:
                raise HTTPException(status_code=404, detail="check category in [role, scene, segemnt]")
        
        if not clone_image or not clone_image.path:
            logger.warning(f"图片记录不存在, category: {category}, id: {image_id}")
            raise HTTPException(status_code=404, detail="Image record not found in database")
    
        file = FilePath(clone_image.path)
        if file.exists():
            return FileResponse(file)

    except Exception as e:
        logger.error(f"获取图片{image_id}失败: {str(e)}")
        logger.exception('获取图片失败')
        raise HTTPException(status_code=404, detail=f"Image not found {str(e)}")

@router.get("/video/{category}/{video_id}")
async def export_image(
    db: SessionDep,
    category: Literal['segment_video', 'merged'] = Path(..., description="视频分类 (src)"), 
    video_id: int = Path(..., description="图片ID")
):
    logger.info(f'receive get image, category:{category}, id:{video_id}')
    try:
        match category:
            case 'segment_video':
                segment_video = db.query(CloneSegmentVideo).filter(CloneSegmentVideo.id == video_id).first()
                file = FilePath(segment_video.path)
            case 'merged':
                merged_video = db.query(CloneVideo).filter(CloneVideo.id == video_id).first()
                file = FilePath(merged_video.file_path)
            case _:
                raise HTTPException(status_code=404, detail="check category in [role, scene, segemnt]")
       
        if file.exists():
            return FileResponse(file)

    except Exception as e:
        logger.error(f"获取图片{video_id}失败: {str(e)}")
        logger.exception('获取图片失败')
        raise HTTPException(status_code=404, detail=f"Image not found {str(e)}")


 
@router.patch("/{category}/{id}/regenerate")
@limiter.limit("1/5second")
async def regenerate_image(
    request: Request,
    session: AsyncSessionDep,
    category: Literal['role', 'scene', 'frame'] = Path(..., description="图片分类 (src)"),
    id: int = Path(..., description="图片ID"),
    payload: ImageRegenerateInput = Body(..., description="生成参数")
):
    logger.info(f'receive regenerate_image, category:{category}, id:{id}, payload: {payload.model_dump()}')
    try:
        data_cls = None
        if category == 'role':
            data_cls = CloneRoleImage
        elif category == 'scene':
            data_cls = CloneSceneImage
        elif category == 'frame':
            data_cls = CloneSegmentImg
        else:
            raise ValueError('check category')
        
        logger.info(f'data_cls is {data_cls}')
        result = await session.execute(
            update(data_cls)
            .where(
                data_cls.id == id,
                data_cls.status != GenerateStatus.PROCESSING
            )
            .values({
                "status": GenerateStatus.PROCESSING
            })
        )
        await session.commit()
        affected_rows = result.rowcount
        
        if affected_rows == 0:
            raise HTTPException(
                status_code=404,
                detail="regenerate_image not found or status is not PROCESSING"
            )
        
        category = REGENERATE_TYPE.IMAGE.value + category
        regenerate_task.delay(category, id, payload.model_dump())
    except HTTPException as e:
        logger.exception('重新生成图片失败')
        raise e
    except Exception as e:
        logger.exception('重新生成图片失败')
        raise HTTPException(status_code=400, detail=f"重新生成图片失败: {str(e)}")
    
@router.get("/{category}/{id}/regenerate", response_model=ImageRegenerateResponse)
async def regenerate_image_status(
    session: AsyncSessionDep,
    category: Literal['role', 'scene', 'frame'] = Path(..., description="分类 (src)"),
    id: int = Path(..., description="图片ID"),
):
    try:
        image_info = None
        match category:
            case 'role':
                res = await session.execute(select(CloneRoleImage).where(CloneRoleImage.id == id))
                image_info = res.scalar_one()
            case 'scene':
                res = await session.execute(select(CloneSceneImage).where(CloneSceneImage.id == id))
                image_info = res.scalar_one()
            case 'frame':
                res = await session.execute(select(CloneSegmentImg).where(CloneSegmentImg.id == id))
                image_info = res.scalar_one()
            case _:
                raise HTTPException(status_code=404, detail='category not find.')
        if not image_info:
            raise HTTPException(status_code=404, detail='category not find.')
        
        logger.info(f'image_info: {vars(image_info)}')
        return ImageRegenerateResponse.model_validate(image_info)
    except HTTPException as e:
        logger.exception('get image status error.')
        raise
    except Exception as e:
        logger.exception('get image status error.')
        raise HTTPException(status_code=400, detail=f"重新生成图片失败: {str(e)}")

@router.post("/voices")
async def clone_voices(request: CloneStoryboardRequest, db: SessionDep):
    try:
        affected_rows = db.query(CloneScript).filter( 
            CloneScript.id == request.clone_script_id, 
            CloneScript.clone_status.in_([CloneStatus.PLOT_DONE, CloneStatus.VOICE_DONE])
            ).update({
                "clone_status": CloneStatus.VOICE,
                "clone_progress": 21,
                "clone_error_message": None
            })
        db.commit()
        if affected_rows == 0:
            raise HTTPException(status_code=404, detail="任务已在运行或状态不正确")


        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        clone_video_task.delay(clone_script.id, 2, request.auto_run)
        return {"id": clone_script.id, "status": clone_script.clone_status, "progress": clone_script.clone_progress}
    except HTTPException as e:
        raise e
    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")
    
@router.post("/segments")
async def clone_segments(request: CloneStoryboardRequest, db: SessionDep):
    try:

        affected_rows = db.query(CloneScript).filter( 
            CloneScript.id == request.clone_script_id, 
            CloneScript.clone_status.in_([CloneStatus.PLOT_DONE, CloneStatus.VOICE_DONE, CloneStatus.SEGMENTS_DONE])
            ).update({
                "clone_status": CloneStatus.SEGMENTS,
                "clone_progress": 31,
                "clone_error_message": None
            })
        db.commit()
        if affected_rows == 0:
            raise HTTPException(status_code=404, detail="任务已在运行或状态不正确")

        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        clone_video_task.delay(clone_script.id, 3, request.auto_run)
        return {"id": clone_script.id, "status": clone_script.clone_status, "progress": clone_script.clone_progress}
    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")
    
@router.post("/images")
async def clone_images(request: CloneStoryboardRequest, db: SessionDep):
    try:
        affected_rows = db.query(CloneScript).filter( 
            CloneScript.id == request.clone_script_id, 
            CloneScript.clone_status.in_([CloneStatus.SEGMENTS_DONE, CloneStatus.IMAGE_DONE])
            ).update({
                "clone_status": CloneStatus.IMAGE,
                "clone_progress": 31,
                "clone_error_message": None
            })
        db.commit()
        if affected_rows == 0:
            raise HTTPException(status_code=404, detail="任务已在运行或状态不正确")
        
        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        clone_video_task.delay(clone_script.id, 4, request.auto_run)
        return {"id": clone_script.id, "status": clone_script.clone_status, "progress": clone_script.clone_progress}

    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")
    
@router.post("/frames")
async def clone_frames(request: CloneStoryboardRequest, db: SessionDep):
    try:
        logger.info(f'clone_frames receive request: {request.model_dump()}')
        affected_rows = db.query(CloneScript).filter( 
            CloneScript.id == request.clone_script_id, 
            CloneScript.clone_status.in_([CloneStatus.IMAGE_DONE, CloneStatus.FRAME_DONE])
            ).update({
                "clone_status": CloneStatus.FRAME,
                "clone_progress": 45,
                "clone_error_message": None
            })
        db.commit()
        if affected_rows == 0:
            raise HTTPException(status_code=404, detail="任务已在运行或状态不正确")
        
        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        clone_video_task.delay(clone_script.id, 5, request.auto_run)
        return {"id": clone_script.id, "status": clone_script.clone_status, "progress": clone_script.clone_progress}

    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")


@router.post("/segment_videos")
async def clone_segment_videos(request: CloneStoryboardRequest, db: SessionDep):
    try:
        logger.info(f'clone_segment_videos receive request: {request.model_dump()}')
        affected_rows = db.query(CloneScript).filter( 
            CloneScript.id == request.clone_script_id, 
            CloneScript.clone_status.in_([CloneStatus.IMAGE_DONE, CloneStatus.FRAME_DONE])
            ).update({
                "clone_status": CloneStatus.SEGMENT_VIDEO,
                "clone_progress": 60,
                "clone_error_message": None
            })
        db.commit()
        if affected_rows == 0:
            raise HTTPException(status_code=404, detail="任务已在运行或状态不正确")
        
        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        clone_video_task.delay(clone_script.id, 6, request.auto_run)
        return {"id": clone_script.id, "status": clone_script.clone_status, "progress": clone_script.clone_progress}

    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")


@router.post("/video")
async def clone_merge_video(request: CloneStoryboardRequest, db: SessionDep):
    try:
        affected_rows = db.query(CloneScript).filter( 
            CloneScript.id == request.clone_script_id, 
            CloneScript.clone_status.in_([CloneStatus.IMAGE_DONE, CloneStatus.FRAME_DONE])
            ).update({
                "clone_status": CloneStatus.MERGE_VIDEO,
                "clone_progress": 95,
                "clone_error_message": None
            })
        db.commit()
        if affected_rows == 0:
            raise HTTPException(status_code=404, detail="任务已在运行或状态不正确")
        
        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        clone_video_task.delay(clone_script.id, 7, request.auto_run)
        return {"id": clone_script.id, "status": clone_script.clone_status, "progress": clone_script.clone_progress}

    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")





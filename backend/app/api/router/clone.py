

import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.database import SessionLocal
from app.models.script import CloneImage, CloneVoice, CloneScript, CloneScriptSegment, CloneVideo, Script, CloneStatus
from app.tasks.parse_video import clone_video_task
from app.util import logger
from app.api.deps import SessionDep


class ClonePlotRequest(BaseModel):
    video_id: int =  Field(..., alias="videoId")
    clone_theme: str =  Field(..., alias="cloneTheme")
    auto_run: bool = Field(default=False, alias="autoRun", description="自动进入下一阶段")
    style: Optional[str] = Field(description="视频风格 不填保持不变")
    product: Optional[str] = Field(description="带货商品 可以不填")
    product_desc: Optional[str] = Field(alias="productDesc", description="商品介绍")

class CloneVoiceRequest(BaseModel):
    clone_script_id: int = Field(..., alias="cloneScriptId")
    auto_run: bool = Field(default=False,  alias="autoRun", description="自动进入下一阶段")

class CloneStoryboardRequest(BaseModel):
    clone_script_id: int = Field(..., alias="cloneScriptId")
    auto_run: bool = Field(default=False, alias="autoRun", description="自动进入下一阶段")

class CloneImageRequest(BaseModel):
    clone_script_id: int = Field(..., alias="cloneScriptId")
    auto_run: bool = Field(default=False,  alias="autoRun", description="自动进入下一阶段")

router = APIRouter(prefix="/clone", tags=["clone"])


@router.post("/plot")
async def clone_plot(request: ClonePlotRequest, db: SessionDep):
    try:
        logger.info(f'receive clone_plot post. auto run is {request.auto_run}')
        script = db.query(Script).filter(Script.video_id == request.video_id).first()
        if not script:
            raise HTTPException(status_code=404, detail="原视频脚本不存在")
        
        full_data = request.model_dump(exclude_none=True, by_alias=False)

        target_keys = {"style", "product", "product_desc"}
        filtered_dict = {k: v for k, v in full_data.items() if k in target_keys}
        clone_requirements = filtered_dict if filtered_dict is not None else None
        kwags = {
            "script_id": script.id,
            "clone_theme": request.clone_theme,
            "clone_status": CloneStatus.PLOT.value,
            "clone_progress": 0
        }
        if clone_requirements is not None:
            kwags["clone_requirements"] = clone_requirements

        clone_script = CloneScript(**kwags)
        
        db.add(clone_script)
        db.commit()
        db.refresh(clone_script)

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
        videos = []

        if clone_script.clone_status in plot_complete_status or \
            (clone_script.clone_status == CloneStatus.FAILED and clone_script.clone_progress >= 20):
            clone_parse_file_path = clone_script.clone_parse_file_path
            if clone_parse_file_path is None:
                raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
            clone_parse_file = Path(clone_parse_file_path)
            print(f'clone_parse_file_path: {clone_parse_file_path}')
            if clone_parse_file.is_file():
                with open(clone_parse_file_path, 'r', encoding='utf-8') as f:
                    clone_script_content = f.read()
                print(f'read plot script: {clone_script_content[:50]}')
                # 正确：使用 CloneVoice 自己的创建时间排序
                voices = db.query(CloneVoice).filter(CloneVoice.script_id == clone_script.id).order_by(CloneVoice.sort_order).all()
                segments = db.query(CloneScriptSegment).filter(CloneScriptSegment.script_id == clone_script.id).order_by(CloneScriptSegment.start_time).all()
                images = db.query(CloneImage).filter(CloneImage.script_id == clone_script.id).order_by(CloneImage.created_at).all()
                videos = db.query(CloneVideo).filter(CloneVideo.video_id == clone_script.id).all()
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
                    "id": img.id,
                    "role_name": img.role_name,
                    "width": img.width,
                    "height": img.height,
                    "desc": img.desc
                }
                for img in images
            ],
            "videos": [
                {
                    "id": video.id
                }
                for video in videos
            ]
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
        path = Path(clone_voice.path)
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
        clone_parse_file = Path(clone_parse_file_path)
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

@router.get("/image/{image_id}")
async def export_image(image_id: int, db: SessionDep):
    logger.info(f'receive get image, id:{image_id}')
    try:
        clone_voice = db.query(CloneImage).filter(CloneImage.id == image_id).first()
        file = Path(clone_voice.path)
        if file.exists():
            return FileResponse(file)

    except Exception as e:
        logger.error(f"获取图片{image_id}失败: {str(e)}")
        logger.exception('获取图片失败')
        raise HTTPException(status_code=404, detail="Image not found")

@router.post("/voices")
async def clone_voices(request: CloneStoryboardRequest, db: SessionDep):
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        if clone_script.clone_status in list(CloneStatus)[:2] or \
            clone_script.clone_status == CloneStatus.FAILED and clone_script.clone_progress < 20:
            raise HTTPException(status_code=400, detail=f"脚本复刻未完成，待完成后再重新生成分镜")
        clone_script.clone_status = CloneStatus.VOICE
        db.commit()
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

        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        if clone_script.clone_status in list(CloneStatus)[:2] or \
            clone_script.clone_status == CloneStatus.FAILED and clone_script.clone_progress < 20:
            raise HTTPException(status_code=400, detail=f"脚本复刻未完成，待完成后再重新生成分镜")
        clone_script.clone_status = CloneStatus.SEGMENTS
        db.commit()
        clone_video_task.delay(clone_script.id, 3, request.auto_run)
        return {"id": clone_script.id, "status": clone_script.clone_status, "progress": clone_script.clone_progress}
    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")
    
@router.post("/images")
async def clone_segments(request: CloneStoryboardRequest, db: SessionDep):
    try:
        clone_script = db.query(CloneScript).filter(CloneScript.id == request.clone_script_id).first()
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        if clone_script.clone_status in list(CloneStatus)[:2] or \
            clone_script.clone_status == CloneStatus.FAILED and clone_script.clone_progress < 20:
            raise HTTPException(status_code=400, detail=f"脚本复刻未完成，待完成后再重新生成分镜")
        clone_script.clone_status = CloneStatus.IMAGE
        db.commit()
        clone_video_task.delay(clone_script.id, 4, request.auto_run)
        return {"id": clone_script.id, "status": clone_script.clone_status, "progress": clone_script.clone_progress}

    except Exception as e:
        print(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")
    
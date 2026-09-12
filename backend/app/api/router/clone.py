
import os
from pathlib import Path as FilePath
from typing import Literal, Optional

from fastapi import APIRouter, Body, HTTPException, Path, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from app.models.script import (
    CloneRoleImage,
    CloneSceneImage,
    CloneSegmentImg,
    GenerateStatus,
    Script,
    CloneStatus,
)
from app.tasks.parse_video import clone_video_task, regenerate_task
from app.util import REGENERATE_TYPE, ImageRegenerateInput, ImageRegenerateResponse, logger
from app.config import settings
from app.api.deps import AsyncSessionDep
from app.api.deps import limiter
from app.api.deps import CurrentActiveUser, CurrentUser
from app.services.ownership import (
    assert_clone_script_access,
    assert_image_access,
    assert_segment_video_access,
    get_owned_script_by_id,
    get_owned_script_by_video,
)
from app.services import clone_service


class ClonePlotRequest(BaseModel):
    # 允许通过原名或别名进行赋值/解析
    model_config = {
        "populate_by_name": True
    }
    video_id: int = Field(..., alias="videoId")
    clone_theme: str = Field(..., alias="cloneTheme")
    auto_run: bool = Field(default=False, alias="autoRun", description="自动进入下一阶段")
    style: Optional[str] = Field(default=None, description="视频风格 不填保持不变")
    product: Optional[str] = Field(default=None, description="带货商品 可以不填")
    product_desc: Optional[str] = Field(alias="productDesc", default=None, description="商品介绍")
    aspect_ratio: Optional[str] = Field(default=None, alias="aspectRatio", description="视频比例 16:9/9:16/1:1")
    generation_method: Optional[Literal['cloud', 'local']] = Field(
        default=None, alias="generationMethod", description="生成方式 cloud=云端API local=本地comfy"
    )


class CloneRequestBase(BaseModel):
    # 允许通过原名或别名进行赋值/解析
    model_config = {
        "populate_by_name": True
    }
    clone_script_id: int = Field(..., alias="cloneScriptId")
    auto_run: bool = Field(default=False, alias="autoRun", description="自动进入下一阶段")


class ReClonePlotRequest(CloneRequestBase):
    pass


class ClonePhaseRequest(CloneRequestBase):
    """推进到指定复刻阶段。step: 2=分镜 3=配音 4=生图 5=参考帧 6=分镜视频 7=合并成片"""

    step: int = Field(..., ge=2, le=7, description="复刻阶段 2-7")


router = APIRouter(prefix="/clone", tags=["clone"])


@router.post("/plot")
@limiter.limit("1/5second")
async def clone_plot(request: Request, request_data: ClonePlotRequest, db: AsyncSessionDep, current_user: CurrentUser):
    try:
        logger.info(f'receive clone_plot post. auto run is {request_data.auto_run}')
        # 归属校验：只能基于自己的视频创建复刻剧本（无权按不存在处理）
        script = await get_owned_script_by_video(db, request_data.video_id, current_user)
        if not script:
            raise HTTPException(status_code=404, detail="原视频脚本不存在")

        full_data = request_data.model_dump(exclude_none=True, by_alias=False)
        target_keys = {"style", "product", "product_desc", "aspect_ratio", "generation_method"}
        filtered_dict = {k: v for k, v in full_data.items() if k in target_keys}
        clone_requirements = filtered_dict if filtered_dict else None

        merge_theme = f'复刻主题：{request_data.clone_theme}   '
        if request_data.product:
            merge_theme += f'推广商品：{request_data.product}   '
            if request_data.product_desc:
                merge_theme += f'商品描述：{request_data.product_desc} '
        
        clone_script = await clone_service.create_clone_script(
            db,
            script_id=script.id,
            clone_theme=merge_theme,
            clone_requirements=clone_requirements,
        )
        # 复刻剧本默认自动跑到分镜(step1+2)并停在 SEGMENTS_DONE；autoRun=true 才继续到成片
        stop_step = 8 if request_data.auto_run else 2
        clone_video_task.delay(clone_script.id, 1, True, stop_step)
        return {
            "id": clone_script.id,
            "theme": merge_theme,
            "status": clone_script.clone_status,
            "progress": clone_script.clone_progress,
        }
    except Exception:
        logger.error(f"复刻失败")
        raise


@router.post("/re_plot")
async def re_clone_plot(request: ReClonePlotRequest, db: AsyncSessionDep, current_user: CurrentUser):
    try:
        logger.info(f'receive re_plot post. auto run is {request.auto_run}')
        # 归属校验：只能重跑自己的复刻剧本
        await assert_clone_script_access(db, request.clone_script_id, current_user)
        ok = await clone_service.reset_clone_plot(db, request.clone_script_id)
        if not ok:
            raise HTTPException(status_code=404, detail="复刻任务已在运行或状态不正确")

        clone_script = await clone_service.get_clone_script(db, request.clone_script_id)
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在，请先生成视频脚本")

        stop_step = 8 if request.auto_run else 2
        clone_video_task.delay(clone_script.id, 1, True, stop_step)
        return {
            "id": clone_script.id,
            "theme": clone_script.clone_theme,
            "status": clone_script.clone_status,
            "progress": clone_script.clone_progress,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")


@router.get("/{clone_script_id}/status")
async def get_clone_status(clone_script_id: int, db: AsyncSessionDep, current_user: CurrentUser):
    try:
        clone_script = await assert_clone_script_access(db, clone_script_id, current_user)
        if not clone_script:
            raise HTTPException(status_code=404, detail="复刻视频脚本不存在")
        return {
            "id": clone_script.id,
            "clone_status": clone_service.clone_status_value(clone_script.clone_status),
            "clone_progress": clone_script.clone_progress or 0,
            "generate_flow_status": clone_service.generate_flow_status_value(clone_script.generate_flow_status),
            "generate_flow_progress": clone_script.generate_flow_progress or 0,
            "error_message": clone_script.clone_error_message,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取状态失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取状态失败: {str(e)}")


@router.get("/list_all")
async def list_all_clone_scripts(db: AsyncSessionDep, current_user: CurrentUser, offset: int = 0, limit: int = 50):
    """列出当前用户可见的复刻剧本，附带原视频信息。"""
    try:
        return await clone_service.list_all_clone_scripts(db, current_user, offset=offset, limit=limit)
    except Exception as e:
        logger.error(f"获取全部复刻脚本列表失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取复刻脚本列表失败: {str(e)}")


@router.get("/{script_id}/list_clone_scripts")
async def list_clone_scripts(script_id: int, db: AsyncSessionDep, current_user: CurrentUser, offset: int = 0, limit: int = 20):
    try:
        # 归属校验：只能列出自己视频脚本下的复刻剧本
        if not await get_owned_script_by_id(db, script_id, current_user):
            raise HTTPException(status_code=404, detail="原视频脚本不存在")
        clone_scripts = await clone_service.list_clone_scripts(db, script_id, offset=offset, limit=limit)
        return [
            {
                "id": cs.id,
                "clone_theme": cs.clone_theme,
                "clone_status": clone_service.clone_status_value(cs.clone_status),
                "clone_progress": cs.clone_progress,
                "generate_flow_status": clone_service.generate_flow_status_value(cs.generate_flow_status),
                "generate_flow_progress": cs.generate_flow_progress or 0,
                "error_message": cs.clone_error_message,
            }
            for cs in clone_scripts
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取复刻脚本列表失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取复刻脚本列表失败: {str(e)}")


@router.get("/capabilities")
async def clone_capabilities():
    """暴露生成能力给前端：是否允许本地 comfy、可选比例与默认值。

    必须注册在 /{clone_script_id} 之前，否则 "capabilities" 会被当作 id 解析。
    docker 部署（RUN_ENV=PRODUCTION）无本地 comfy 服务，只允许云端 API 生成。
    """
    return {
        "allow_local_comfy": not settings.is_production,
        "default_method": "cloud",
        "default_aspect_ratio": "16:9",
        "aspect_ratios": ["16:9", "9:16", "1:1"],
    }


@router.get("/{clone_script_id}")
async def get_clone_script_detail(clone_script_id: int, db: AsyncSessionDep, current_user: CurrentUser):
    try:
        logger.info(f'receive get_clone_script. clone_script_id is {clone_script_id}')
        # 归属校验：普通用户只能查看自己的复刻剧本（无权按不存在处理）
        await assert_clone_script_access(db, clone_script_id, current_user)
        return await clone_service.get_clone_script_detail(db, clone_script_id)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception('error')
        logger.error(f"获取复刻脚本信息失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取复刻脚本信息失败: {str(e)}")


@router.get("/voice/{voice_id}")
async def export_voice(voice_id: int, db: AsyncSessionDep, current_user: CurrentUser):
    """
    传入 voice id，返回音频文件流（前端可通过 Blob 接收）
    """
    try:
        logger.info(f'receive get voice, id:{voice_id}')
        clone_voice = await clone_service.get_voice(db, voice_id)
        if not clone_voice:
            raise HTTPException(status_code=404, detail="音频记录不存在")
        # 归属校验：配音属于某个复刻剧本，经其父级判定
        await assert_clone_script_access(db, clone_voice.script_id, current_user)
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取复刻脚本信息失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"获取音频失败: {str(e)}")


@router.get("/{clone_script_id}/export/plot")
async def export_clone_script(clone_script_id: int, db: AsyncSessionDep, current_user: CurrentUser):
    try:
        # 归属校验必须在读取文件之前完成
        clone_script = await assert_clone_script_access(db, clone_script_id, current_user)
        plot_complete_status = list(CloneStatus)[2:]
        if clone_script.clone_status not in plot_complete_status:
            raise HTTPException(status_code=400, detail=f"脚本复刻未完成，待完成后下载")

        clone_parse_file_path = clone_script.clone_parse_file_path
        if clone_parse_file_path is None:
            raise HTTPException(status_code=404, detail="复刻视频脚本未生成")
        clone_parse_file = FilePath(clone_parse_file_path)
        logger.info(f'clone_parse_file_path: {clone_parse_file_path}')
        if clone_parse_file.is_file():
            return FileResponse(
                path=clone_parse_file_path,
                filename=f"clone_{clone_script_id}.md",
                media_type="text/markdown"
            )
        else:
            raise HTTPException(status_code=404, detail="复刻视频脚本未生成")

    except HTTPException:
        # 如果是主动抛出的 HTTPException，直接继续往外抛，不拦截、不拼接
        raise
    except Exception as e:
        logger.error(f"导出复刻脚本信息失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"导出复刻脚本信息失败: {str(e)}")


@router.get("/image/{category}/{image_id}")
async def export_image(
    db: AsyncSessionDep,
    current_user: CurrentUser,
    category: Literal['role', 'scene', 'frame'] = Path(..., description="图片分类 (src)"),
    image_id: int = Path(..., description="图片ID")
):
    logger.info(f'receive get image, category:{category}, id:{image_id}')
    try:
        clone_image = await clone_service.get_image_by_category(db, category, image_id)
        if not clone_image or not clone_image.path:
            logger.warning(f"图片记录不存在, category: {category}, id: {image_id}")
            raise HTTPException(status_code=404, detail="Image record not found in database")
        # 归属校验：图片属于某个复刻剧本（frame 经其分镜判定）
        await assert_image_access(db, category, clone_image, current_user)

        file = FilePath(clone_image.path)
        if file.exists():
            return FileResponse(file)
        raise HTTPException(status_code=404, detail="Image file not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取图片{image_id}失败: {str(e)}")
        logger.exception('获取图片失败')
        raise HTTPException(status_code=404, detail=f"Image not found {str(e)}")


@router.get("/video/{category}/{video_id}")
async def export_video(
    db: AsyncSessionDep,
    current_user: CurrentUser,
    category: Literal['segment_video', 'merged'] = Path(..., description="视频分类 (src)"),
    video_id: int = Path(..., description="视频ID")
):
    logger.info(f'receive get video, category:{category}, id:{video_id}')
    try:
        obj, file_path = await clone_service.get_video_by_category(db, category, video_id)
        if not obj or not file_path:
            raise HTTPException(status_code=404, detail="Video record not found in database")
        # 归属校验：分镜视频经其分镜判定，成片直接对应复刻剧本
        if category == 'segment_video':
            await assert_segment_video_access(db, obj, current_user)
        else:
            await assert_clone_script_access(db, obj.video_id, current_user)
        file = FilePath(file_path)
        if file.exists():
            return FileResponse(file)
        raise HTTPException(status_code=404, detail="Video file not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取视频{video_id}失败: {str(e)}")
        logger.exception('获取视频失败')
        raise HTTPException(status_code=404, detail=f"Video not found {str(e)}")


@router.patch("/{category}/{id}/regenerate")
@limiter.limit("1/5second")
async def regenerate_image(
    request: Request,
    session: AsyncSessionDep,
    current_user: CurrentActiveUser,
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
        # 归属校验：只能重试自己名下的图片（必须在任何变更之前）
        image_info = await clone_service.get_image_by_category(session, category, id)
        if not image_info:
            raise HTTPException(status_code=404, detail="regenerate_image not found")
        await assert_image_access(session, category, image_info, current_user)

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
    current_user: CurrentUser,
    category: Literal['role', 'scene', 'frame'] = Path(..., description="分类 (src)"),
    id: int = Path(..., description="图片ID"),
):
    try:
        image_info = await clone_service.get_image_by_category(session, category, id)
        if not image_info:
            raise HTTPException(status_code=404, detail='category not find.')
        # 归属校验：普通用户只能查询自己名下的图片状态
        await assert_image_access(session, category, image_info, current_user)

        logger.info(f'image_info: id={image_info.id}, status={image_info.status}, version={image_info.version}')
        return ImageRegenerateResponse.model_validate(image_info)
    except HTTPException as e:
        logger.exception('get image status error.')
        raise
    except Exception as e:
        logger.exception('get image status error.')
        raise HTTPException(status_code=400, detail=f"重新生成图片失败: {str(e)}")


@router.post("/phase")
async def clone_phase(request: ClonePhaseRequest, db: AsyncSessionDep, current_user: CurrentUser):
    """推进复刻到指定阶段（合并原 voices/segments/images/frames/segment_videos/video 六个接口）。

    step: 2=分镜 3=配音 4=生图 5=参考帧 6=分镜视频 7=合并成片
    兼容前端：路径使用 `/clone/phase`，body 中带 cloneScriptId/autoRun/step。
    """
    try:
        logger.info(f'clone_phase receive request: {request.model_dump()}')
        # 未激活账号不能生成配音/图片/视频（step 3..7）；step 2(分镜) 放行
        if request.step >= 3 and not current_user.is_active:
            raise HTTPException(status_code=403, detail="账号未激活，请联系管理员激活")
        # 归属校验：只能推进自己的复刻剧本
        await assert_clone_script_access(db, request.clone_script_id, current_user)
        clone_script = await clone_service.advance_clone_step(db, request.clone_script_id, request.step)
        # 配音完成后、进入会用时间的阶段（生图/分镜视频）前，先校准分镜时间轴（幂等），
        # 保证下游拿到的分镜时长与真实音轨一致。voice 图结束时已校准一次，这里兜底旧状态。
        # 注：step 7 合并时视频已生成，不重排，避免与已有分镜视频脱节。
        if request.step in (4, 6):
            await clone_service.sync_segment_timeline(request.clone_script_id, db=db)
        clone_video_task.delay(clone_script.id, request.step, request.auto_run)
        return {
            "id": clone_script.id,
            "status": clone_script.clone_status,
            "progress": clone_script.clone_progress,
            "generate_flow_status": clone_script.generate_flow_status,
            "generate_flow_progress": clone_script.generate_flow_progress
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"复刻失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"复刻失败: {str(e)}")

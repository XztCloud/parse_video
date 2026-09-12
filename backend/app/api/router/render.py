from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import AsyncSessionDep
from app.api.deps import limiter
from app.api.deps import CurrentActiveUser
from app.services import clone_service
from app.services.ownership import get_owned_video
from app.tasks.parse_video import clone_video_task
from app.util import logger


class RenderFromScriptRequest(BaseModel):
    # 允许通过原名或别名进行赋值/解析
    model_config = {
        "populate_by_name": True
    }
    video_id: int = Field(..., alias="videoId")


router = APIRouter(prefix="/render", tags=["render"])


@router.post("/from-script")
@limiter.limit("1/5second")
async def render_from_script(request: Request, request_data: RenderFromScriptRequest, db: AsyncSessionDep, current_user: CurrentActiveUser):
    """输出视频模块：以原片解析出的剧本+分镜为输入，一键渲染成片。

    创建 ORIGINAL 渲染工作台（source_type=ORIGINAL，中性主题"原片直转"），
    复用 clone_graph 自动跑 plot→storyboard→voice→image→video→merge。
    """
    try:
        logger.info(f'receive render from-script. video_id is {request_data.video_id}')
        # 归属校验：只能基于自己的视频创建渲染工作台（无权按不存在处理）
        if not await get_owned_video(db, request_data.video_id, current_user):
            raise HTTPException(status_code=404, detail="视频不存在")
        workspace = await clone_service.create_original_render(db, request_data.video_id)
        clone_video_task.delay(workspace.id, 1, True)
        return {
            "id": workspace.id,
            "theme": workspace.clone_theme,
            "source_type": workspace.source_type,
            "status": workspace.clone_status,
            "progress": workspace.clone_progress,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"原片渲染失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"原片渲染失败: {str(e)}")
import asyncio
import os, uuid
from urllib.parse import urlparse
import aiofiles
from fastapi import APIRouter, Request, UploadFile, File, HTTPException, status
from pydantic import BaseModel, field_validator

from app.api.deps import AsyncSessionDep
from ...models.video import VideoSource
from ...config import settings
from ...tasks.parse_video import parse_video_task
from ...services.douyin_parser import DouyinParser
from ...services.video_service import create_video_record, video_to_dict, get_video_by_id, list_videos as list_video_records
from app.util import MAX_DURATION_SECONDS, MAX_FILE_SIZE, get_video_duration_ffprobe, logger, is_video_file
from app.api.deps import limiter

router = APIRouter(prefix="/videos", tags=["videos"])

# 允许的抖音相关域名（含短链与 CDN）
ALLOWED_DOUYIN_DOMAINS = (
    "douyin.com",
    "www.douyin.com",
    "v.douyin.com",
    "iesdouyin.com",
    "www.iesdouyin.com",
    "douyinvod.com",
    "amemv.com",
)

class DouyinRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def validate_douyin_url(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("url 不能为空")
        url = v.strip()
        parsed = urlparse(url)
        # 仅允许 http/https
        if parsed.scheme not in ("http", "https"):
            raise ValueError("仅支持 http/https 链接")
        host = (parsed.hostname or "").lower()
        # 短链可能以 www. 开头，统一去掉 www. 再判断
        bare_host = host[4:] if host.startswith("www.") else host
        if not any(host.endswith(d) or bare_host.endswith(d) for d in ALLOWED_DOUYIN_DOMAINS):
            raise ValueError("仅允许抖音视频链接")
        return url

@router.post("/upload")
@limiter.limit("1/5second")
async def upload_video(request: Request, db: AsyncSessionDep, file: UploadFile = File(...)):

    # 文件扩展名校验
    if not file.filename.lower().endswith((".mp4", ".mov", ".avi", ".mkv")):
        raise HTTPException(status_code=400, detail="不支持的视频格式")
    # 如果请求头里包含了 content-length 并且超标，直接拒绝
    if file.size and file.size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="文件体积超过 200MB 限制")
    abs_file_path = ''
    try:
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
        ext = os.path.splitext(file.filename)[1].lower()
        if not ext:
            ext = ".mp4"
        filename = f"{uuid.uuid4()}{ext}"
        file_path = os.path.join(settings.UPLOAD_DIR, filename)

        total_written = 0
        async with aiofiles.open(file_path, "wb") as f:
            while content := await file.read(1024 * 1024):  # 每次读 1MB
                total_written += len(content)
                # 边写边校验实际文件体积，防止恶意绕过 Content-Length
                if total_written > MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"传输文件过大，已超过上限 200MB"
                    )
                await f.write(content)
        abs_file_path = os.path.abspath(file_path)

        # 用 ffprobe 校验文件确实是视频（不只看扩展名，防止伪造扩展名的恶意文件）
        if not is_video_file(abs_file_path):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="文件不是有效的视频文件（无法解析出视频流）"
            )

        duration = await asyncio.to_thread(get_video_duration_ffprobe, abs_file_path)

        if duration > MAX_DURATION_SECONDS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"视频时长过长 ({duration:.1f} 秒)，不能超过 {int(MAX_DURATION_SECONDS)} 秒（3 分钟）"
            )

        video = await create_video_record(
            db, title=file.filename, file_path=abs_file_path
        )
        parse_video_task.delay(video.id)
        return video_to_dict(video)
    except ValueError as e:
        if os.path.exists(abs_file_path):
            os.remove(abs_file_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法解析视频文件: {str(e)}"
        )
    except Exception as e:
        if os.path.exists(abs_file_path):
            os.remove(abs_file_path)
        logger.exception(f'upload file failed. {str(e)}')
        raise HTTPException(status_code=400, detail=f"上传文件失败: {str(e)}")


@router.post("/douyin")
@limiter.limit("1/5second")
async def parse_douyin(request: Request, request_data: DouyinRequest, db: AsyncSessionDep):
    try:
        logger.info("parse douyin url: %s", request_data.url)
        file_path, title = await asyncio.to_thread(DouyinParser.download_video, request_data.url)

        video = await create_video_record(
            db,
            title=title,
            file_path=file_path,
            source_type=VideoSource.DOUYIN,
            source_url=request_data.url,
        )
        parse_video_task.delay(video.id)
        return video_to_dict(video)

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"抖音链接解析失败: {str(e)}")

@router.get("")
async def list_videos(db: AsyncSessionDep, skip: int = 0, limit: int = 20):
    try:
        videos = await list_video_records(db, skip=skip, limit=limit)
        return [video_to_dict(v) for v in videos]
    except Exception as e:
        logger.exception(f'list_videos failed. ')
        raise HTTPException(status_code=400, detail=f"获取视频列表失败: {str(e)}")

@router.get("/{video_id}/status")
async def get_video_status(video_id: int, db: AsyncSessionDep):
    try:
        video = await get_video_by_id(db, video_id)
        if not video:
            raise HTTPException(status_code=404, detail="视频不存在")
        return video_to_dict(video)
    except Exception as e:
        logger.exception(f'get_video_status failed. ')
        raise HTTPException(status_code=400, detail=f"获取视频{video_id}状态失败: {str(e)}")

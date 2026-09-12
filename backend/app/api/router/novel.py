"""小说API路由

提供小说上传、生成、状态查询、列表等API端点。
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AsyncSessionDep, CurrentUser
from app.config import settings
from app.models.novel import Novel
from app.models.script import CloneScript
from app.util import make_dir, logger

router = APIRouter(prefix="/novel", tags=["novel"])


# ==================== Request/Response Models ====================

class NovelUploadResponse(BaseModel):
    """小说上传响应"""
    id: int
    title: str
    chapter_count: Optional[int] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class NovelGenerateRequest(BaseModel):
    """小说生成请求"""
    novelId: int
    theme: str
    autoRun: bool = False
    requirements: Optional[dict] = None


class NovelCreateRequest(BaseModel):
    """小说文本创建请求"""
    title: str
    content: str


class NovelGenerateResponse(BaseModel):
    """小说生成响应"""
    novelId: int
    status: str
    clone_script_ids: list[int]


class NovelStatusResponse(BaseModel):
    """小说状态响应"""
    id: int
    title: str
    status: str
    progress: int
    error_message: Optional[str] = None
    chapter_count: Optional[int] = None
    script_count: int = 0
    created_at: datetime

    class Config:
        from_attributes = True


class NovelListItem(BaseModel):
    """小说列表项"""
    id: int
    title: str
    chapter_count: Optional[int] = None
    status: str
    progress: int
    created_at: datetime

    class Config:
        from_attributes = True


class CloneScriptListItem(BaseModel):
    """CloneScript列表项"""
    id: int
    clone_theme: Optional[str] = None
    clone_status: str
    clone_progress: int
    source_type: str
    chapter_index: Optional[int] = None
    chapter_title: Optional[str] = None
    scene_index: Optional[int] = None

    class Config:
        from_attributes = True


# ==================== API Endpoints ====================

@router.post("/upload", response_model=NovelUploadResponse)
async def upload_novel(
    db: AsyncSessionDep,
    file: UploadFile = File(...),
    title: str = Form(...),
):
    """上传小说文件

    Args:
        file: 小说文件（支持.txt, .md格式）
        title: 小说标题

    Returns:
        NovelUploadResponse
    """
    # 验证文件格式
    allowed_extensions = {'.txt', '.md', '.markdown'}
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_ext}。支持的格式: {', '.join(allowed_extensions)}"
        )

    # 读取文件内容
    content = await file.read()
    try:
        text_content = content.decode('utf-8')
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码不是UTF-8")

    # 保存文件到磁盘
    upload_dir = Path(settings.UPLOAD_DIR) / "novels"
    make_dir(str(upload_dir))

    # 生成唯一文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{file.filename}"
    file_path = upload_dir / filename

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(text_content)

    # 创建Novel记录
    novel = Novel(
        title=title,
        file_path=str(file_path),
        raw_content=text_content,
        status="PENDING",
        progress=0,
    )
    db.add(novel)
    await db.commit()
    await db.refresh(novel)

    logger.info(f"Novel uploaded: {novel.id} - {novel.title}")

    return NovelUploadResponse(
        id=novel.id,
        title=novel.title,
        chapter_count=novel.chapter_count,
        status=novel.status,
        created_at=novel.created_at,
    )


@router.post("/create", response_model=NovelUploadResponse)
async def create_novel_from_text(
    db: AsyncSessionDep,
    request: NovelCreateRequest,
):
    """通过粘贴文本创建小说

    Args:
        request: NovelCreateRequest (title + content)

    Returns:
        NovelUploadResponse
    """
    if not request.content.strip():
        raise HTTPException(status_code=400, detail="小说内容不能为空")

    if len(request.content) > 50000:
        raise HTTPException(status_code=400, detail="小说内容不能超过50000字")

    # 保存文本到文件
    upload_dir = Path(settings.UPLOAD_DIR) / "novels"
    make_dir(str(upload_dir), re_create=False)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{request.title}.txt"
    file_path = upload_dir / filename

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(request.content)

    # 创建Novel记录
    novel = Novel(
        title=request.title,
        file_path=str(file_path),
        raw_content=request.content,
        status="PENDING",
        progress=0,
    )
    db.add(novel)
    await db.commit()
    await db.refresh(novel)

    logger.info(f"Novel created from text: {novel.id} - {novel.title}")

    return NovelUploadResponse(
        id=novel.id,
        title=novel.title,
        chapter_count=novel.chapter_count,
        status=novel.status,
        created_at=novel.created_at,
    )


@router.post("/generate", response_model=NovelGenerateResponse)
async def generate_novel_scripts(
    db: AsyncSessionDep,
    request: NovelGenerateRequest,
):
    """触发小说转剧本生成

    Args:
        request: NovelGenerateRequest

    Returns:
        NovelGenerateResponse
    """
    from app.tasks.parse_video import novel_generate_task

    # 检查小说是否存在
    novel = await db.get(Novel, request.novelId)
    if not novel:
        raise HTTPException(status_code=404, detail=f"Novel with id {request.novelId} not found")

    
    result = await db.execute(
        update(Novel)
        .where(
            Novel.id == request.novelId,
            Novel.status != 'PROCESSING'
        )
        .values({
            "status": 'PROCESSING'
        })
    )
    await db.commit()
    affected_rows = result.rowcount

    if affected_rows == 0:
        raise HTTPException(
            status_code=404,
            detail="generate_novel_scripts status is not PROCESSING"
        )

    # 启动Celery任务
    task = novel_generate_task.delay(
        novel_id=request.novelId,
        theme=request.theme,
        requirements=request.requirements,
        auto_run=request.autoRun,
    )

    logger.info(f"Novel generation task started: {task.id}")

    return NovelGenerateResponse(
        novelId=request.novelId,
        status="PROCESSING",
        clone_script_ids=[],  # 任务启动时还没有生成scripts
    )


@router.get("/{novel_id}/status", response_model=NovelStatusResponse)
async def get_novel_status(
    db: AsyncSessionDep,
    novel_id: int,
):
    """获取小说处理状态

    Args:
        novel_id: 小说ID

    Returns:
        NovelStatusResponse
    """
    novel = await db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"Novel with id {novel_id} not found")

    # 统计生成的CloneScript数量
    result = await db.execute(
        select(func.count(CloneScript.id))
        .where(CloneScript.novel_id == novel_id)
    )
    script_count = result.scalar() or 0

    return NovelStatusResponse(
        id=novel.id,
        title=novel.title,
        status=novel.status,
        progress=novel.progress,
        error_message=novel.error_message,
        chapter_count=novel.chapter_count,
        script_count=script_count,
        created_at=novel.created_at,
    )


@router.get("/{novel_id}/scripts", response_model=list[CloneScriptListItem])
async def get_novel_scripts(
    db: AsyncSessionDep,
    novel_id: int,
):
    """获取小说生成的所有CloneScript

    Args:
        novel_id: 小说ID

    Returns:
        CloneScriptListItem列表
    """
    # 检查小说是否存在
    novel = await db.get(Novel, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail=f"Novel with id {novel_id} not found")

    # 查询所有CloneScript
    result = await db.execute(
        select(CloneScript)
        .where(CloneScript.novel_id == novel_id)
        .order_by(CloneScript.id)
    )
    scripts = result.scalars().all()

    # 构建响应
    items = []
    for script in scripts:
        # 从clone_requirements中提取元数据
        requirements = script.clone_requirements or {}
        items.append(CloneScriptListItem(
            id=script.id,
            clone_theme=script.clone_theme,
            clone_status=script.clone_status.value if hasattr(script.clone_status, 'value') else script.clone_status,
            clone_progress=script.clone_progress,
            source_type=script.source_type,
            chapter_index=requirements.get("chapter_index"),
            chapter_title=requirements.get("chapter_title"),
            scene_index=requirements.get("scene_index"),
        ))

    return items


@router.get("/list_all", response_model=list[NovelListItem])
async def list_all_novels(
    db: AsyncSessionDep,
    skip: int = 0,
    limit: int = 20,
):
    """获取所有小说列表

    Args:
        skip: 跳过数量
        limit: 限制数量

    Returns:
        NovelListItem列表
    """
    result = await db.execute(
        select(Novel)
        .order_by(Novel.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    novels = result.scalars().all()

    return [
        NovelListItem(
            id=novel.id,
            title=novel.title,
            chapter_count=novel.chapter_count,
            status=novel.status,
            progress=novel.progress,
            created_at=novel.created_at,
        )
        for novel in novels
    ]

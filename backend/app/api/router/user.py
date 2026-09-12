

from datetime import datetime
import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import select

from app.api.deps import AsyncSessionDep, CurrentSuperUser, CurrentUser
from app.api.security import get_password_hash
from app.models.user import User


logger = logging.getLogger("parse_video")


router = APIRouter(prefix="/users", tags=["users"])

class UserBase(BaseModel):
    email: EmailStr = Field(max_length=255)
    full_name: str | None = Field(default=None, max_length=255)

class UserCreate(UserBase):
    # 拒绝多余字段（如 is_superuser），使越权赋值直接 422 而不是被静默忽略
    model_config = ConfigDict(extra="forbid")

    password: str = Field(min_length=8, max_length=128)

class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None

class UserDetail(UserPublic):
    """含激活/管理员标记的用户信息（用于 /users/me 与管理员列表）"""
    is_active: bool
    is_superuser: bool

class UserActiveUpdate(BaseModel):
    """管理员更新账号激活状态：只允许改 is_active，is_superuser 任何接口都不可写"""
    model_config = ConfigDict(extra="forbid")

    is_active: bool


def _to_user_detail(user: User) -> UserDetail:
    # is_active / is_superuser 列可空，统一归一化成 bool（None 视为 False）
    return UserDetail(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        created_at=user.created_at,
        is_active=bool(user.is_active),
        is_superuser=bool(user.is_superuser),
    )


@router.post("", response_model=UserPublic)
async def create_user(db: AsyncSessionDep, user_create: UserCreate):
    """自助注册：一律创建普通且未激活的账号，需管理员激活后才能生成内容"""
    result = await db.execute(select(User).where(User.email == user_create.email))
    user = result.scalar_one_or_none()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system."
        )
    hashed_password = get_password_hash(user_create.password)
    kwargs = {k: v for k, v in user_create.model_dump().items() if k in User.__table__.columns}
    new_user = User(**kwargs, hashed_password=hashed_password, is_active=False, is_superuser=False)

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    logger.info("created new user id=%s email=%s", new_user.id, new_user.email)
    kwargs = {k: v for k, v in vars(new_user).items() if k in UserPublic.model_fields.keys()}

    return UserPublic.model_validate(kwargs)


@router.get("/me", response_model=UserDetail)
async def read_user_me(current_user: CurrentUser):
    """当前登录账号信息（含 is_active / is_superuser，供前端做权限展示）

    注意：本路由必须声明在任何 /users/{...} 之前。
    """
    return _to_user_detail(current_user)


@router.get("", response_model=list[UserDetail])
async def list_users(db: AsyncSessionDep, current_user: CurrentSuperUser):
    """管理员：列出全部账号"""
    result = await db.execute(select(User).order_by(User.created_at))
    return [_to_user_detail(user) for user in result.scalars().all()]


@router.patch("/{user_id}/active", response_model=UserDetail)
async def update_user_active(
    user_id: uuid.UUID,
    payload: UserActiveUpdate,
    db: AsyncSessionDep,
    current_user: CurrentSuperUser,
):
    """管理员：激活/停用账号（只改 is_active）"""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    user.is_active = payload.is_active
    await db.commit()
    await db.refresh(user)
    logger.info("admin=%s set user=%s is_active=%s", current_user.email, user.email, payload.is_active)
    return _to_user_detail(user)


@router.delete("/{user_id}", status_code=204)
async def delete_user(
    user_id: uuid.UUID,
    db: AsyncSessionDep,
    current_user: CurrentSuperUser,
):
    """管理员：删除账号；其名下资产（视频/小说及其全部下游）由数据库级联删除。"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.is_superuser:
        raise HTTPException(status_code=400, detail="不能删除管理员账号")
    email = user.email
    # videos.user_id / novels.user_id 均为 ON DELETE CASCADE，
    # 删除用户会级联删除其视频→脚本→复刻剧本→配音/图片/视频，以及小说→剧本章节。
    await db.delete(user)
    await db.commit()
    logger.info("admin=%s deleted user=%s", current_user.email, email)

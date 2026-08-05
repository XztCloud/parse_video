

from datetime import datetime
import logging
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select

from app.api.deps import AsyncSessionDep
from app.api.security import get_password_hash
from app.models.user import User


logger = logging.getLogger("parse_video")


router = APIRouter(prefix="/users", tags=["users"])

class UserBase(BaseModel):
    email: EmailStr = Field(max_length=255)
    full_name: str | None = Field(default=None, max_length=255)

class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)

class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None

@router.post("", response_model=UserPublic)
async def create_user(db: AsyncSessionDep, user_create: UserCreate):
    result = await db.execute(select(User).where(User.email == user_create.email))
    user = result.scalar_one_or_none()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system."
        )
    hashed_password = get_password_hash(user_create.password)
    kwargs = {k: v for k, v in user_create.model_dump().items() if k in User.__table__.columns}
    new_user = User(**kwargs, hashed_password=hashed_password)

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    logger.info("created new user id=%s email=%s", new_user.id, new_user.email)
    kwargs = {k: v for k, v in vars(new_user).items() if k in UserPublic.model_fields.keys()}

    return UserPublic.model_validate(kwargs)


from datetime import timedelta
from typing import Annotated, Any

import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CurrentUser, AsyncSessionDep
from app.api.security import create_access_token, verify_password
from app.config import settings
from app.models.user import Token, User
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.router.user import UserPublic

logger = logging.getLogger("parse_video")

router = APIRouter(prefix="/login",
                   tags=["login"],)

DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"

async def authenticate(session: AsyncSession,  email: str, password: str) -> User | None:
    logger.info("authenticate: email=%s", email)
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        # 防止猜测邮箱，增加执行时长
        verify_password(password, DUMMY_HASH)
        return None
    verified, updated_password_hash = verify_password(password, user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        user.hashed_password = updated_password_hash
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user

@router.post("/access-token")
async def login_access_token(
    response: Response,
    session: AsyncSessionDep,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """

    user = await authenticate(
        session=session, email=form_data.username, password=form_data.password
    )
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect email or password")
    # elif not user.is_active:
    #     raise HTTPException(status_code=400, detail="Inactive user")
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token=create_access_token(
        user.id, expires_delta=access_token_expires
    )
    token = Token(
        access_token=access_token
    )

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,   # 如果现网使用https 再使用 settings.is_production,
        samesite="lax",
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return token


@router.post("/logout")
async def logout(response: Response):
    # 发送一个值为空、max_age=0 的同名 Cookie，强制浏览器立即删除它
    response.set_cookie(
        key="access_token",
        value="",
        httponly=True,
        secure=False,  # 如果现网使用https 再使用 settings.is_production,
        samesite="lax",
        path="/",
        max_age=0,     # 关键：设置为 0 立即过期
    )
    return {"detail": "Successfully logged out"}

@router.post("/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    """
    Test access token
    """
    return current_user

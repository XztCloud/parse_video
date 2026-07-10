from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import SessionDep
from app.api.security import create_access_token, verify_password
from app.config import settings
from app.models.user import Token, User
from sqlalchemy.orm import Session

router = APIRouter(prefix="/login",
                   tags=["login"],)

DUMMY_HASH = "$argon2id$v=19$m=65536,t=3,p=4$MjQyZWE1MzBjYjJlZTI0Yw$YTU4NGM5ZTZmYjE2NzZlZjY0ZWY3ZGRkY2U2OWFjNjk"

def authenticate(session: Session,  email: str, password: str) -> User | None:
    print(f'email: {email}, password:{password}')
    user = session.query(User).filter(User.email == email).first()
    if not user:
        # 防止猜测邮箱，增加执行时长
        verify_password(password, DUMMY_HASH)
        return None
    print(f'find user verify_password')
    verified, updated_password_hash = verify_password(password, user.hashed_password)
    if not verified:
        return None
    if updated_password_hash:
        user.hashed_password = updated_password_hash
        session.add(user)
        session.commit()
        session.refresh(user)
    return user

@router.post("/access-token")
async def login_access_token(
    response: Response,
    session: SessionDep, 
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()]
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """

    user = authenticate(
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
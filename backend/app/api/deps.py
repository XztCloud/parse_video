from collections.abc import Generator
from typing import Annotated
from fastapi import Cookie, Depends, HTTPException, Header, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from pydantic import ValidationError
from app.database import AsyncSessionLocal, SessionLocal
from sqlalchemy.orm import Session
from fastapi import Depends, HTTPException

from app.api.security import ALGORITHM
from app.config import settings

from jwt.exceptions import InvalidTokenError

from app.models.user import TokenPayload, User

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

async def get_async_db():
    async with AsyncSessionLocal() as db:
        yield db

SessionDep = Annotated[Session, Depends(get_db)]

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"api/v1/login/access-token",
    auto_error=False
)

async def get_token(
    bearer_token: Annotated[str | None, Depends(reusable_oauth2)],
    access_token: Annotated[str | None, Cookie()] = None,
) -> str:
    # 1. 优先读取 Authorization Header
    if bearer_token:
        return bearer_token

    # 2. 再读取 Cookie
    if access_token:
        print(f'find access_token: {access_token}')
        return access_token

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
    )

TokenDep = Annotated[str, Depends(get_token)]

async def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
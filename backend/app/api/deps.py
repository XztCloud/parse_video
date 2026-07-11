from collections.abc import Generator
from typing import Annotated
from fastapi import Cookie, Depends, HTTPException, Header, Request, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from pydantic import ValidationError
from slowapi import Limiter
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

async def get_current_user(request: Request, session: SessionDep, token: TokenDep) -> User:
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
    request.state.user_id=user.id
    return user

CurrentUser = Annotated[User, Depends(get_current_user)]


def get_token_from_request(request: Request) -> str | None:
    authorization = request.headers.get("Authorization")
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer":
            return credentials

    token = request.cookies.get("access_token")
    if token and token.startswith("Bearer "):
        token = token[7:]

    return token

def user_id_identifier(request: Request) -> str:
    user_id = request.state.user_id
    print(f'get user_id_identifier: {user_id}')
    if user_id:
        return f"user:{user_id}:{request.url.path}"
    return f"ip:{request.client.host}:{request.url.path}"


limiter = Limiter(key_func=user_id_identifier, storage_uri=settings.REDIS_URL)

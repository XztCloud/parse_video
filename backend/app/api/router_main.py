from fastapi import APIRouter, Depends

from app.api.router import videos
from app.api.router import clone, scripts, user, login
from app.api.deps import get_current_user


api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(user.router)

# 创建一个【专门需要鉴权】的中转路由组 全局拦截，按需获取 CurrentUser
authenticated_router = APIRouter(dependencies=[Depends(get_current_user)])
authenticated_router.include_router(scripts.router)
authenticated_router.include_router(videos.router)
authenticated_router.include_router(clone.router)

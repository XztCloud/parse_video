from fastapi import APIRouter

from app.api.router import videos
from app.api.router import clone, scripts, user, login


api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(scripts.router)
api_router.include_router(videos.router)
api_router.include_router(clone.router)
api_router.include_router(user.router)

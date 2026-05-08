from fastapi import APIRouter

from app.api import scripts, videos


api_router = APIRouter()
api_router.include_router(scripts.router)
api_router.include_router(videos.router)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .config import settings
import os
from app.api.router_main import api_router

app = FastAPI(title="视频脚本解析平台", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(api_router)

from .database import Base, engine
from .models import video, script

@app.on_event("startup")
def startup():
    Base.metadata.create_all(bind=engine)
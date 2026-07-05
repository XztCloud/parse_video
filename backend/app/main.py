from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
from app.api.__init__ import __api_version__
from app.util import get_env_value, configure_logging, logger
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


def create_app() -> FastAPI:
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """管理 fastAPI 开始和结束 生命周期"""

        try:
            logger.info('Server is ready to accept connections!')

            yield
        
        finally:
            logger.info('Server stop!')

    app_kwargs = {
        'title': 'parse_video',
        'version': __api_version__,
        'lifespan': lifespan,
        'openapi_url': '/api/v1/openapi.json'
    }

    app = FastAPI(**app_kwargs)

    if settings.all_cors:
        app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
        

    app.include_router(api_router, prefix='/api/v1')
    return app


def main():
    # 配置日志
    configure_logging(settings.LOG_ENABLED)
    logger.setLevel(settings.LOG_LEVEL)
    if settings.LOG_ENABLED:
        logger.disabled = False
    else:
        logger.disabled = True
    logger.info("Logging is configured. Starting the server...")

    app = create_app()
    uvicorn_config = {
        "app": app,  # Pass application instance directly instead of string path
        "host": settings.BACKEND_HOST,
        "port": settings.BACKEND_PORT,
        "log_config": None,
    }
    logger.info(f'uvicorn_config: {uvicorn_config}')
    uvicorn.run(**uvicorn_config)

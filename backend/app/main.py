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
from app.api.router_main import api_router, authenticated_router
from slowapi import  _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.api.deps import limiter


os.makedirs(settings.UPLOAD_DIR, exist_ok=True)


from .database import Base, engine


def create_app() -> FastAPI:
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """管理 fastAPI 开始和结束 生命周期"""

        try:
            # Base.metadata.create_all(bind=engine)  创建遗漏数据表。dev环境，线上使用alembic 替代
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

    if settings.is_production:
        app_kwargs.update({
            'docs_url': None,     # 关闭 /docs
            'redoc_url': None,    # 关闭 /redoc
            'openapi_url': None   # 关闭 /openapi.json (核心！防止被爬取接口结构)
        })

    app = FastAPI(**app_kwargs)

    if settings.all_cors:
        app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.include_router(api_router, prefix='/api/v1')
    app.include_router(authenticated_router, prefix='/api/v1')
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
        "app": app,  # 如果使用多进程，这里不要传对象，改成生成路径，并添加workers参数
        "host": settings.BACKEND_HOST,
        "port": settings.BACKEND_PORT,
        "log_config": None,
    }
    logger.info(f'uvicorn_config: {uvicorn_config}')
    uvicorn.run(**uvicorn_config)

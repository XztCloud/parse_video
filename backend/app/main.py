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


from .database import Base, engine, async_engine


def create_app() -> FastAPI:
    
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        """管理 fastAPI 开始和结束 生命周期"""

        try:
            # Base.metadata.create_all(bind=engine)  创建遗漏数据表。dev环境，线上使用alembic 替代
            logger.info('Server is ready to accept connections!')

            yield
        
        finally:
            await async_engine.dispose()
            logger.info('Server stop!')

    app_kwargs = {
        'title': 'parse_video',
        'version': __api_version__,
        'lifespan': lifespan,
    }

    if settings.is_production:
        # 生产环境：关闭所有文档页面，防止接口结构被爬取
        app_kwargs.update({
            'docs_url': None,     # 关闭 /docs
            'redoc_url': None,    # 关闭 /redoc
            'openapi_url': None   # 关闭 /openapi.json
        })
    else:
        # 开发/测试环境：启用文档页面
        app_kwargs.update({
            'docs_url': '/docs',           # Swagger UI
            'redoc_url': '/redoc',         # ReDoc
            'openapi_url': '/openapi.json' # OpenAPI JSON
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

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


app = create_app()


def main():
    # 配置日志
    configure_logging(settings.LOG_ENABLED)
    logger.setLevel(settings.LOG_LEVEL)
    if settings.LOG_ENABLED:
        logger.disabled = False
    else:
        logger.disabled = True
    logger.info("Logging is configured. Starting the server...")

    uvicorn_config = {
        "app": "app.main:app",
        "host": settings.BACKEND_HOST,
        "port": settings.BACKEND_PORT,
        "log_config": None,
    }
    logger.info(f'uvicorn_config: {uvicorn_config}')
    uvicorn.run(**uvicorn_config)

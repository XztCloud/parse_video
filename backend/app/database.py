from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import NullPool
from .config import settings
import asyncpg

# 同步引擎仅供 prestart 脚本使用，NullPool 避免 FastAPI 服务中维持无用连接池
engine = create_engine(str(settings.DATABASE_URL), poolclass=NullPool)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 在fastAPI自动维护一个loop可以使用这种全局变量的session, celery 不要使用全局session
# 1. 使用 create_async_engine 代替 create_engine
# 确保 settings.DATABASE_URL 使用的是异步驱动（如 postgresql+asyncpg）
async_engine = create_async_engine(str(settings.ASYNC_DATABASE_URL), echo=False, pool_pre_ping=True,)

# 2. sessionmaker 配置中必须指定 class_=AsyncSession
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    pass



from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from .config import settings
import asyncpg

print(f'settings.DATABASE_URL: {settings.DATABASE_URL}')
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 1. 使用 create_async_engine 代替 create_engine
# 确保 settings.DATABASE_URL 使用的是异步驱动（如 postgresql+asyncpg）
async_engine = create_async_engine(settings.ASYNC_DATABASE_URL, echo=True)

# 2. sessionmaker 配置中必须指定 class_=AsyncSession
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
)

class Base(DeclarativeBase):
    pass



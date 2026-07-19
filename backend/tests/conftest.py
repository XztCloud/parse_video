


import asyncio
from collections.abc import AsyncGenerator
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from app.database import Base
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import AsyncSessionLocal
import pytest

from app.prestart.create_admin import async_init
from app.models.video import Video

from pathlib import Path
from unittest.mock import patch
from app.models.script import Script
from app.models.user import User
from app.models.voice import VoiceInfoCollect
from app.main import create_app
from tests.commons.utils import get_admin_token_headers

Path("logs").mkdir(exist_ok=True)

# 因为是异步接口 替代 from fastapi.testclient import TestClient
@pytest.fixture(scope="session")
async def client() -> AsyncGenerator[AsyncClient]:
    # 使用 ASGITransport 直接把请求转发给 FastAPI，不需要真实启动网络端口，速度极快
    test_app = create_app()
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://") as ac:
        yield ac


@pytest.fixture(scope="session", autouse=True)
async def db() -> AsyncGenerator[AsyncSession]:
    await async_init()
    async with AsyncSessionLocal() as session:

        yield session
        
        statement = delete(Video)
        await session.execute(statement=statement)
        
        statement = delete(User)
        await session.execute(statement=statement)
        
        statement = delete(VoiceInfoCollect)
        await session.execute(statement=statement)
        
        await session.commit()
        
@pytest.fixture(scope="module")
async def superuser_token_headers(client: AsyncClient) -> dict[str, str]:
    return await get_admin_token_headers(client)


@pytest.fixture
def mock_parse_video_task():
    with patch("app.api.router.videos.parse_video_task.delay") as mock:
        yield mock
        
@pytest.fixture
def mock_clone_video_task():
    with patch("app.api.router.clone.clone_video_task.delay") as mock:
        yield mock
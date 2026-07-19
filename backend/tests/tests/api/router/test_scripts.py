from pathlib import Path

from httpx import ASGITransport, AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.commons.runner_utils import run_usecase

@pytest.mark.api
async def test_scripts_yaml(client: AsyncClient, db: AsyncSession, superuser_token_headers:dict[str, str]):
    """测试scriptes接口

    Args:
        client (AsyncClient): 测试api客户端
        db (AsyncSession): 数据库
        superuser_token_headers (dict[str, str]): 鉴权
    """
    current_path = Path(__file__).resolve().parent / 'scripts.yaml'
    await run_usecase(current_path, client, db, superuser_token_headers)
    
    
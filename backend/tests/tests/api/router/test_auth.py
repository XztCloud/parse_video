import logging
from pathlib import Path


import pytest

from tests.conftest import superuser_token_headers
from tests.commons.yaml_utils import load_yaml
from tests.commons.runner_utils import run_usecase, runner
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger('test')


@pytest.mark.auth
async def test_auth_yaml(client: AsyncClient, db: AsyncSession, superuser_token_headers:dict[str, str]):
    """测试认证接口

    Args:
        client (AsyncClient): 测试客户端
        db (AsyncSession): 数据库
        superuser_token_headers (dict[str, str]): 鉴权
    """
    current_path = Path(__file__).resolve().parent / 'auth.yaml'
    await run_usecase(current_path, client, db, superuser_token_headers)

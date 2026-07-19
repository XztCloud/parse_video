import logging
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.commons.runner_utils import run_usecase
from tests.commons.yaml_utils import load_yaml
from unittest.mock import MagicMock

logger = logging.getLogger('test')

@pytest.mark.api
async def test_clone_yaml(mock_clone_video_task:MagicMock, client: AsyncClient, db: AsyncSession, superuser_token_headers:dict[str, str]):
    """执行clone api测试用例

    Args:
        client (AsyncClient): 请求客户端
        db (AsyncSession): 数据库
        superuser_token_headers (dict[str, str]): 带认证的请求头
    """
    current_path = Path(__file__).resolve().parent / 'clone.yaml'
    await run_usecase(current_path, client, db, superuser_token_headers)
    
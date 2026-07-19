
import random
import string

from app.config import settings
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

async def get_admin_token_headers(client: AsyncClient) -> dict[str, str]:
    """测试环境获取用户token

    Args:
        client (TestClient): fastapi 提供的测试客户端

    Returns:
        dict[str, str]: 返回带认证的headers
    """
    login_data = {
        "username": settings.SUPER_ADMINI_EMAIL,
        "password": settings.SUPER_ADMINI_PASSWORD,
    }
    r = await client.post(f'api/v1/login/access-token', data=login_data)
    tokens = r.json()
    print(f'tokens is {tokens}')
    a_token = tokens['access_token']
    headers = {"Authorization": f"Bearer {a_token}"}
    return headers


def random_lower_string() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=32))


def random_email() -> str:
    return f"{random_lower_string()}@{random_lower_string()}.com"





import re


TYPE_MAP = {
    "int": int,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "float": float,
}


def get_value(data, path):
    """
    data.user.name
    """
    obj = data

    for key in path.split("."):
        obj = obj[key]

    return obj


def validate(resp: dict, rules: dict):

    for path, rule in rules.items():

        value = get_value(resp, path) if path else resp
        print(f'value:{value}, path:{path}, rule: {rule}')

        # ------------------------
        # type
        # ------------------------
        if "type" in rule:
            expect = TYPE_MAP[rule["type"]]
            assert isinstance(value, expect), \
                f"{path} should be {rule['type']}"

        # ------------------------
        # eq
        # ------------------------
        if "eq" in rule:
            print(f'123value: {value},  expext: {rule["eq"]}')
            assert value == rule["eq"], \
                f"{path} expect {rule['eq']} got {value}"

        # ------------------------
        # ne
        # ------------------------
        if "ne" in rule:
            assert value != rule["ne"]

        # ------------------------
        # not_null
        # ------------------------
        if rule.get("not_null"):
            assert value is not None

        # ------------------------
        # not_empty
        # ------------------------
        if rule.get("not_empty"):
            assert value not in ("", [], {}, (), None)

        # ------------------------
        # gt
        # ------------------------
        if "gt" in rule:
            assert value > rule["gt"]

        if "ge" in rule:
            assert value >= rule["ge"]

        if "lt" in rule:
            assert value < rule["lt"]

        if "le" in rule:
            assert value <= rule["le"]

        # ------------------------
        # startswith
        # ------------------------
        if "startswith" in rule:
            assert value.startswith(rule["startswith"])

        # ------------------------
        # endswith
        # ------------------------
        if "endswith" in rule:
            assert value.endswith(rule["endswith"])

        # ------------------------
        # contains
        # ------------------------
        if "contains" in rule:
            assert rule["contains"] in value

        # ------------------------
        # regex
        # ------------------------
        if "regex" in rule:
            assert re.match(rule["regex"], value)

        # ------------------------
        # length
        # ------------------------
        if "len" in rule:
            assert len(value) == rule["len"]

        if "len_gt" in rule:
            assert len(value) > rule["len_gt"]

        if "len_ge" in rule:
            assert len(value) >= rule["len_ge"]

        if "len_lt" in rule:
            assert len(value) < rule["len_lt"]

        if "len_le" in rule:
            assert len(value) <= rule["len_le"]

        # ------------------------
        # in
        # ------------------------
        if "in" in rule:
            assert value in rule["in"]

        # ------------------------
        # not in
        # ------------------------
        if "not_in" in rule:
            assert value not in rule["not_in"]
            
        if "each" in rule:

            for index, item in enumerate(value):
                validate(item, rule["each"])
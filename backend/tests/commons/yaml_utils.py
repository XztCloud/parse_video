
import logging
from pathlib import Path

import yaml
from app.config import settings
from app.models.user import User

logger = logging.getLogger('test')

def settings_constructor(loader, node):
    # node.value 获取到的就是标签后面的字符串，比如 "COMFY_USER"
    attr_name = loader.construct_scalar(node)
    # 动态去 settings 实例中获取这个属性值
    return getattr(settings, attr_name, f"未找到属性:{attr_name}")

def func_constructor(loader, node):
    value = loader.construct_scalar(node)
    parts = value.split()
    return {
        "__type__": "function",
        "name": parts[0],
        "args": parts[1:]
    }

def load_yaml(path: Path | str) -> str:
    # 将这个构造器注册到 PyYAML 中
    yaml.SafeLoader.add_constructor('!settings', settings_constructor)
    yaml.SafeLoader.add_constructor('!func', func_constructor)
    data = ''
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    logger.info(f'get yaml data is {data}   type is {type(data)}')
    return data




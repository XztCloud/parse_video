import asyncio
import logging
from pathlib import Path
import re
from unittest.mock import patch
import responses_validator
from fastapi.testclient import TestClient

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from pwdlib.hashers.bcrypt import BcryptHasher
from app.models.user import User
from app.api.security import verify_password
from app.models.script import CloneScript, CloneStatus, Script, ScriptSegment
from app.models.video import Video, VideoSource, VideoStatus
from tests.commons.yaml_utils import load_yaml
from tests.commons.utils import random_email, random_lower_string, validate
from tests.commons.extra_utils import extract
from app.config import settings

logger = logging.getLogger('test')

random_eamil = ''
random_pawword = ''
async def gen_user_bcrythasher(db: AsyncSession, *args, **kwargs):
    """生成使用bcrypt加密的用户
    """
    global random_eamil, random_pawword
    random_eamil = random_email()
    random_pawword = random_lower_string()
    
    # Create a bcrypt hash directly (simulating legacy password)
    bcrypt_hasher = BcryptHasher()
    bcrypt_hash = bcrypt_hasher.hash(random_pawword)
    assert bcrypt_hash.startswith("$2")  # bcrypt hashes start with $2

    user = User(email=random_eamil, hashed_password=bcrypt_hash, is_active=True)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    assert user.hashed_password.startswith("$2")
    return {"username": random_eamil, "password": random_pawword}
    

async def get_verify(db: AsyncSession,  *args, **kwargs):
    res = await db.execute(select(User).where(User.email==random_eamil))
    user = res.scalars().first()
    logger.info(f'user is {vars(user)}')
    assert user != None
    logger.info(f'user.hashed_password is {user.hashed_password}')
    assert user.hashed_password.startswith("$argon2")
    logger.info(f'random_pawword is {random_pawword}')
    verified, updated_hash = verify_password(random_pawword, user.hashed_password)
    logger.info(f'verified is {verified}')
    assert verified
    logger.info(f'updated_hash is {updated_hash}')
    # Should not need another update since it's already argon2
    assert updated_hash is None
    
async def gen_fake_file(*args, **kwargs):
    return ("test_movie.mp4", "fake movie file", "video/mp4")
    
async def prepare_scripts_simple(db: AsyncSession, save_data: dict, *args, **kwargs):
    video = Video(
        title='test',
        file_path='test',
        status=VideoStatus.PENDING,
        progress=0,
        source_type=VideoSource.DOUYIN,
        source_url='test'
    )
    db.add(video)
    await db.commit()
    await db.refresh(video)
    script = Script(video_id=video.id)
    db.add(script)
    await db.commit()
    await db.refresh(script)
    save_data['video_id'] = video.id
    save_data['script_id'] = script.id
    logger.info(f'create video:{video.id}, script:{script.id}')
        
async def prepare_scripts_normal(db: AsyncSession, save_data: dict, *args, **kwargs):
    file_path = str(Path(settings.UPLOAD_DIR + "/test.txt").absolute())
    logger.info(f'create file path: {file_path}')
    with open(file_path, 'w') as f:
        f.write('this is a test file')
    script_id = save_data['script_id']
    res = await db.execute(select(Script).where(Script.id == script_id))
    script = res.scalars().first()
    script.parse_file_path = file_path
    
    for i in range(3):
        seg = ScriptSegment(script_id=script_id, start_time=0.0, end_time=1.0)
        db.add(seg)
    await db.commit()

async def wait_limiter(*args, **kwargs) -> float:
    """防止测试用例触发限流

    Returns:
        float: 等待时长
    """
    await asyncio.sleep(5.5)
    return 5.5

async def prepare_plot_data(db: AsyncSession, save_data: dict, *args, **kwargs) -> dict:
    """准备POST plot 请求参数

    Args:
        db (AsyncSession): 数据库
        save_data (dict): 单yaml用例 持久化上下文

    Returns:
        dict: 请求参数
    """
    await prepare_scripts_simple(db, save_data, *args, **kwargs)
    save_data['theme'] = '测试主题'
    return {'video_id': save_data['video_id'], 'clone_theme': save_data['theme']}

async def check_plot_db(db: AsyncSession, save_data: dict, *args, **kwargs):
    """校验plot完成后数据库内容

    Args:
        db (AsyncSession): 数据库
        save_data (dict): 单yaml用例 持久化上下文

    Returns:
        None: 无返回
    """
    statement = select(CloneScript).where(CloneScript.script_id == save_data['script_id'])
    res = await db.execute(statement=statement)
    clone_script = res.scalars().first()
    assert isinstance(clone_script, CloneScript)
    assert clone_script.clone_progress == 0
    assert clone_script.clone_theme == save_data['theme']
    assert clone_script.clone_status == CloneStatus.PLOT
    assert clone_script.script_id == save_data['script_id']
    
    save_data['clone_script_id'] = clone_script.id
    

FUNCTIONS = {
    "gen_user_bcrythasher": gen_user_bcrythasher,
    "get_verify": get_verify,
    "gen_fake_file": gen_fake_file,
    "prepare_scripts_simple": prepare_scripts_simple,
    "prepare_scripts_normal": prepare_scripts_normal,
    "wait_limiter": wait_limiter,
    "prepare_plot_data": prepare_plot_data,
    "check_plot_db": check_plot_db,
}


async def runner(
        k: str, v: any, save_data: dict, client: AsyncClient, 
        superuser_token_headers: dict[str, str]|None=None,
        db: AsyncSession=None
    ) -> None:
    """执行yaml测试脚本

    Args:
        k (str): yaml中的步骤类别
        v (any): 该步骤对应参数
        save_data (dict): 保存返回结果
        client (TestClient): fastapi 测试客户端
        superuser_token_headers (dict[str, str] | None): access_token,测试login时可以不传
        db (AsyncSession): 数据库对象
    """
    
    context = {
        'save_data': save_data,
        "client": client,
        "superuser_token_headers":superuser_token_headers,
        "db":db,
    }
    
    match k:
        case 'request':
            # 发送请求
            logger.info('1. 正在发送请求')
            logger.info(f'before resolve:{v}')
            v = await resolve_value(v, context)
            logger.info(f'save_data is {save_data}')
            v["url"] = replace_var(v["url"], save_data)
            logger.info(f'after resolve: {v}')
            if v.get('no_headers', False) or not superuser_token_headers:
                save_data['resp'] = await client.request(
                    **{k: v for k, v in v.items() if k != 'no_headers'}
                )
            else:
                save_data['resp'] = await client.request(
                    **v, headers=superuser_token_headers
                )
                logger.info(f'headers: {save_data['resp'].headers.items()}')
                
        case 'response':
            # 断言响应
            logger.info('2.正在断言响应')
            
            status_code = v.get('status_code', None)
            headers = v.get('headers', None)
            json_data = v.get('json', None)
            
            if status_code:
                logger.info(f'断言响应 status_code: {save_data['resp'].status_code}  expect: {status_code}')
                assert status_code == save_data['resp'].status_code
            
            if headers:
                logger.info(f'ori headers: {headers}')
                headers = replace_var(headers, save_data)
                logger.info(f'断言响应 headers data {dict(save_data['resp'].headers)}  expect:{headers}')
                validate(dict(save_data['resp'].headers), headers)
            
            if json_data:
                json_data = replace_var(json_data, save_data)
                logger.info(f'断言响应 json data{save_data['resp'].json()}  expect:{json_data}')
                validate(save_data['resp'].json(), json_data)
            
            # responses_validator.validator(save_data['resp'], **v)
        case 'extract':
            # 变量提取
            logger.info('正在提取变量')
            for var_name, var_exp in v.items():
                value = extract(save_data['resp'], *var_exp)
                logger.info(f'{var_name} = {value}')
                save_data[var_name] = value
        case 'validate':
            # 断言变量
            logger.info(f'validate. after resolve, data is {v}')
            for _k, _v in v.items():
                assert save_data.get(_k) == _v
        case 'option':
            v = await resolve_value(v, context)
                
                
async def resolve_value(value, context):
    if isinstance(value, dict):
        if value.get("__type__") == "function":
            func_name = value['name']
            args = value.get('args', [])
            
            func = FUNCTIONS[func_name]
            
            return await func(*args, **context)
        return {
            k: await resolve_value(v, context)
            for k, v in value.items()
        }
        
    if isinstance(value, list):
        return [
            await resolve_value(v, context)
            for v in value
        ]

    return value


def replace_var(text: str, save_data: dict):
    return re.sub(
        r"\$\{(.*?)\}",
        lambda m: str(save_data[m.group(1)]),
        text,
    )
    
def replace_var(data, save_data: dict):
    if isinstance(data, str):
        return re.sub(
            r"\$\{(.*?)\}",
            lambda m: str(save_data[m.group(1)]),
            data,
        )
    elif isinstance(data, dict):
        return {k: replace_var(v, save_data) for k, v in data.items()}
    elif isinstance(data, list):
        return [replace_var(item, save_data) for item in data]
    else:
        return data


async def run_usecase(yaml_path: str|Path, client: AsyncClient, db: AsyncSession, superuser_token_headers:dict[str, str]):
    
    yaml_data = load_yaml(yaml_path)
    save_data = {}
    for use_case in yaml_data:
        save_data['resp'] = None
        logger.info(f'开始执行用例：{use_case['name']}')
        for step in use_case['steps']:
            logger.info(f'step: {step}, type is {type(step)}')
            for k, v in step.items():
                logger.info(f'k: {k}, v: {v}')
                await runner(k, v, save_data, client, db=db, superuser_token_headers=superuser_token_headers)
                if save_data['resp']:
                    logger.info(f'resopnse: {save_data['resp'].json()}, status_code: {save_data['resp'].status_code}')
                

import asyncio
import enum
import functools
import hashlib
import logging
import os
from pathlib import Path
import re
import shutil
import threading
import time
from typing import Optional
from PIL import Image
import ffmpeg
import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import settings
from app.models.script import GenerateStatus

DEFAULT_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_LOG_BACKUP_COUNT = 5

MAX_DURATION_SECONDS = 180.0 # 最大允许时长：3分钟 (180秒)
MAX_FILE_SIZE = 200 * 1024 * 1024 # 最大允许文件大小：200 MB

logger = logging.getLogger("parse_video")

class REGENERATE_TYPE(enum.Enum):
    """重新生成分类 """
    PLOT = 'plot.'
    VOICE = 'voice.'
    SEGMENT = 'segment.'
    IMAGE = 'image.'
    VOIDE = 'video.'
    
class ImageRegenerateInput(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4096, description="提示词")
    width: int | None = Field(
        default=None, 
        ge=512, 
        le=1920, 
        multiple_of=8, # 限制必须是 8 的倍数（如 512, 520, 528...）
        description="图片宽度"
    )
    height: int | None = Field(
        default=None, 
        ge=512, 
        le=1920, 
        multiple_of=8, # 限制必须是 8 的倍数（如 512, 520, 528...）
        description="图片高度"
    )
    seed: str | None = Field(
        default=None,
        pattern=r"^\d+$",  # 确保传入的是纯数字字符串
        description="随机种子"
    )
    
class ImageRegenerateResponse(BaseModel):
    # 允许从 ORM 对象/类属性中直接加载数据
    model_config = ConfigDict(from_attributes=True)
    status: GenerateStatus = Field(default=GenerateStatus.PENDING, description='图片生成状态')
    id: int = Field(..., description='图片id')
    width: int = Field(..., description='图片宽度')
    height: int = Field(..., description='图片高度')
    prompt: str = Field(..., description='图片提示词')
    seed: str|None = Field(default=None, description="随机种子")
    version: int = Field(..., description='版本号')
    
    @field_validator('seed', mode='before')
    @classmethod
    def convert_seed_to_str(cls, v):
        if v is not None:
            return str(v)  # ✅ 在验证前自动把 int 转换成 str
        return v
    

def make_dir(dir_path: str|Path, re_create: bool=True):
    target_dir = Path(dir_path)
    
    if target_dir.exists() and re_create:
        # 如果存在，使用 rmtree 递归删除该文件夹及其内部的所有子文件和子文件夹
        shutil.rmtree(target_dir)
        
    # 重新创建这个文件夹
    # parents=True: 如果上级目录不存在，会自动连同上级目录一起创建
    # exist_ok=True: 防御性参数，防止高并发下创建瞬间冲突报错
    target_dir.mkdir(parents=True, exist_ok=True)


def retry_on_httpx_error(func=None, *, retries: int=3, delay: float=1.0):
    """
    异步重试装饰器(针对httpx.HTTPError)
    """
    def outter(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try_cnt = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except httpx.HTTPError as e:
                    try_cnt += 1
                    if try_cnt > retries:
                        print(f"[{func.__name__}] 已达到最大重试次数 ({retries})，抛出异常。")
                        raise
                    print(f"[{func.__name__}] 捕获异常，正在进行第 {try_cnt}/{retries} 次重试...")
                    await asyncio.sleep(delay)
        return wrapper
    
    # 情况 A：如果直接以 @retry_on_httpx_error 使用（不带括号）
    # 此时第一个参数 func 就是被装饰的函数本身
    if func is not None:
        return outter(func)
    
    # 情况 B：如果以 @retry_on_httpx_error(retries=5) 使用（带括号）
    # 此时 func 是 None，我们需要返回真正的装饰器函数本身
    return outter

def async_retry_error(func=None, *, retries:int=3, delay:float=1.0):
    def outter(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            try_cnt = 0
            while True:
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    try_cnt += 1
                    if try_cnt > retries:
                        print(f"[{func.__name__}] 已达到最大重试次数 ({retries})，抛出异常。")
                        raise
                    print(f"[{func.__name__}] 捕获异常，正在进行第 {try_cnt}/{retries} 次重试...")
                    await asyncio.sleep(delay)
        return wrapper
    
    if func is not None:
        return outter(func)
    
    return outter


def retry_error(func=None, *, retries:int=3, delay:float=1.0):
    def outter(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try_cnt = 0
            while True:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    try_cnt += 1
                    if try_cnt > retries:
                        print(f"[{func.__name__}] 已达到最大重试次数 ({retries})，抛出异常。")
                        raise e
                    print(f"[{func.__name__}] 捕获异常，正在进行第 {try_cnt}/{retries} 次重试...")
                    time.sleep(delay)
        return wrapper
    
    if func is not None:
        return outter(func)
    
    return outter


def timeout(seconds):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            result = [None]
            exception = [None]

            def target():
                try:
                    result[0] = func(*args, **kwargs)
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=target)
            thread.daemon = True
            thread.start()
            thread.join(seconds)

            if thread.is_alive():
                raise TimeoutError(f"函数 {func.__name__} 执行超过 {seconds} 秒")
            if exception[0]:
                raise exception[0]
            return result[0]
        return wrapper
    return decorator


def calculate_duration_units(text: str):
    # 1. 提取英文单词（按单词计，加单引号支持 don't 等词）
    en_words = re.findall(r"[A-Za-z']+", text)
    en_count = len(en_words)
    
    # 2. 提取数字（把连续的数字当成一个整体，例如 "100" 算一个数字单位）
    # 如果你的业务里数字都是按个读（一零零），可以去掉后面的加号改为 r"\d"
    num_words = re.findall(r"\d+", text)
    num_count = len(num_words)
    
    # 3. 提取中文字符（精确匹配汉字，绝对不包含英文和数字）
    cn_chars = re.findall(r"[\u4e00-\u9fa5]", text)
    cn_count = len(cn_chars)
    
    # 4. 提取标点符号（用于回归模型的另一个特征，或者直接加权）
    punc_chars = re.findall(r"[，。！？、；：, .!?]", text)
    punc_count = len(punc_chars)
    
    # 5. 按照你的公式计算核心文本权重 (这里把数字也暂按中文 1.0 或 英文 0.6 估算，推荐 1.0 偏安全)
    duration_units = cn_count + (en_count * 0.6) + (num_count * 1.0)
    
    return {
        "char_count": round(duration_units),
        "punc_count": punc_count
    }

def get_env_value(key: str, default: any, val_type: type=str) -> any:
    value = os.getenv(key)
    if value is None:
        return default
    
    if value.lower == 'None':
        return None
    
    if val_type is bool:
        return value.lower() in ("true", "1", "yes", "t", "on")
    
    try:
        return val_type(value)
    except (ValueError, TypeError):
        return default
    

def configure_logging(log_enabled: bool):
    for logger_name in ["parse_video",
                        "uvicorn", "uvicorn.access", 
                        "uvicorn.error", "sqlalchemy",
                        "celery", "celery.task"]:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.DEBUG if log_enabled else logging.CRITICAL)

    log_dir = settings.LOG_DIR
    log_file_path = os.path.abspath(os.path.join(log_dir, "parse_video.log"))
    sql_log_path = os.path.abspath(os.path.join(log_dir, "sql.log"))
    celery_log_path = os.path.join(os.path.join(log_dir, "celery.log"))

    os.makedirs(log_dir, exist_ok=True)
    log_max_bytes = get_env_value("LOG_MAX_BYTES", DEFAULT_LOG_MAX_BYTES, int)
    log_backup_count = get_env_value("LOG_BACKUP_COUNT", DEFAULT_LOG_BACKUP_COUNT, int)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(levelname)s: %(message)s",
                },
                "detailed": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "console": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stderr",
                },
                "file": {
                    "formatter": "detailed",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": log_file_path,
                    "maxBytes": log_max_bytes,
                    "backupCount": log_backup_count,
                    "encoding": "utf-8",
                },
                "file_sql": {
                    "formatter": "detailed",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": sql_log_path,
                    "maxBytes": log_max_bytes,
                    "backupCount": log_backup_count,
                    "encoding": "utf-8",
                },
                "file_celery": {
                    "formatter": "detailed",
                    "class": "logging.handlers.RotatingFileHandler",
                    "filename": celery_log_path,  # 独立存储到 celery.log
                    "maxBytes": log_max_bytes,
                    "backupCount": log_backup_count,
                    "encoding": "utf-8",
                },

            },
            "loggers": {
                # Configure all uvicorn related loggers
                "uvicorn": {
                    "handlers": ["console"],
                    "level": "INFO",
                    "propagate": False,
                },
                "sqlalchemy": {
                    "handlers": ["console", "file_sql"],
                    "level": "INFO",
                    "propagate": False,
                },
                "parse_video": {
                    "handlers": ["console", "file"],
                    "level": "INFO",
                    "propagate": False,
                },
                "celery": {
                    "handlers": ["console", "file_celery"],
                    "level": "INFO",
                    "propagate": False,
                },
                "celery.task": {
                    "handlers": ["console", "file_celery"],
                    "level": "INFO",
                    "propagate": False,
                }
            },
            "root": {
                "handlers": ["console", "file"],
                "level": "INFO"
            }
        }
    )


def get_md5(content: str) -> str:
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def get_image_info(file_path):
    """判断是否为图片并返回宽高"""
    try:
        with Image.open(file_path) as img:
            # 获取图片格式和尺寸
            width, height = img.size
            format = img.format
            return {
                'is_image': True,
                'width': width,
                'height': height,
                'format': format
            }
    except Exception:
        # 不是图片或无法读取
        return {
            'is_image': False,
            'width': None,
            'height': None,
            'format': None
        }
        
def get_video_duration_ffprobe(save_path: str) -> float:
    """使用 ffprobe 读取视频时长

    Args:
        save_path (str): 文件路径

    Returns:
        float: 视频时长
    """
    try:
        probe = ffmpeg.probe(save_path)
        
        if 'format' in probe and 'duration' in probe['format']:
            return float(probe['format']['duration'])

        # 备用方案：如果 format 中没有，尝试从第一个 video 流中提取 duration
        video_streams = [s for s in probe.get('streams', []) if s.get('codec_type') == 'video']
        if video_streams and 'duration' in video_streams[0]:
            return float(video_streams[0]['duration'])
            
        raise ValueError("视频文件中未能找到有效的时长信息 (duration)")
    
    except ffmpeg.Error as e:
        error_msg = e.stderr.decode('utf-8') if e.stderr else str(e)
        raise ValueError(f"FFprobe 解析视频失败: {error_msg}")
    
    

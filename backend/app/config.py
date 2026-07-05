from typing import Annotated, Any, List

from pydantic import BeforeValidator, computed_field
from pydantic_settings import BaseSettings

def parse_cors(v: Any) -> List[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [s.strip() for s in v.split(",")]
    if isinstance(v, str | list):
        return v
    raise ValueError(v)

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5433/parse_video"
    REDIS_URL: str = "redis://localhost:6380/0"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024
    ALIYUN_ASR_APP_KEY: str = ""
    ALIYUN_ASR_ACCESS_KEY: str = ""
    ALIYUN_ASR_ACCESS_SECRET: str = ""
    DASHSCOPE_API_KEY: str = ""
    MAX_CONCURRENT_TASKS: int = 3
    BYTEDANCE_APP_ID: str = ""
    BYTEDANCE_TOKEN: str = ""

    BYTEDANCE_AK: str = ""
    BYTEDANCE_SK: str = ""

    BYTEDANCE_API_KEY: str = ""
    
    PUBLIC_API_URL: str = ""
    PUBLIC_API_PREFIX: str

    LLM_NAME: str = ""
    LLM_BASE_URL: str = ""
    LLM_API_KEY: str = ""

    IMAGE_MODEL_NAME: str = ""
    IMAGE_MODEL_API_KEY: str = ""
    IMAGE_MODEL_BASE_URL: str = ""

    STORYBOARD_TRY_COUNT: int = 3

    LOG_DIR: str = ""
    LOG_ENABLED: bool = False
    LOG_LEVEL: str = ""

    FRONTEND_HOST: str = ''
    BACKEND_CORS_ORIGINS: Annotated[str | list, BeforeValidator(parse_cors)] = []

    BACKEND_HOST: str=""
    BACKEND_PORT: int = 8000
    
    class Config:
        env_file = "../.env"

    @computed_field
    @property
    def all_cors(self) -> list[str]:
        return [str(s).rstrip('/') for s in self.BACKEND_CORS_ORIGINS] + [self.FRONTEND_HOST]


settings = Settings()
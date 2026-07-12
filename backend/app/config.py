from pathlib import Path
from typing import Annotated, Any, List
from urllib.parse import urljoin

from pydantic import BeforeValidator, PostgresDsn, computed_field
from pydantic_settings import BaseSettings

def parse_cors(v: Any) -> List[str] | str:
    if isinstance(v, str) and not v.startswith("["):
        return [s.strip() for s in v.split(",")]
    if isinstance(v, str | list):
        return v
    raise ValueError(v)

class Settings(BaseSettings):
    REDIS_URL: str = "redis://localhost:6380/0"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024
    ALIYUN_ASR_APP_KEY: str = ""
    ALIYUN_ASR_ACCESS_KEY: str = ""
    ALIYUN_ASR_ACCESS_SECRET: str = ""
    MAX_CONCURRENT_TASKS: int = 3
    BYTEDANCE_APP_ID: str = ""
    BYTEDANCE_TOKEN: str = ""

    BYTEDANCE_AK: str = ""
    BYTEDANCE_SK: str = ""

    BYTEDANCE_API_KEY: str = ""

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

    SECRET_KEY: str =""
    
    ACCESS_TOKEN_EXPIRE_MINUTES: int= 60

    RUN_ENV: str = "DEV"

    SUPER_ADMINI_EMAIL: str
    SUPER_ADMINI_PASSWORD: str

    POSTGRES_SERVER: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: str
    POSTGRES_DB: str

    COMFY_URL: str
    COMFY_USER: str
    COMFY_PASSWORD: str
    USER_COMFY_IMAGE: bool=False
        
    class Config:
        env_file = "../.env"


    @computed_field
    @property
    def comfy_ws_url(self) -> str:
        url_without_protocol = self.COMFY_URL.split("//")[-1]
        if "https" in self.COMFY_URL:
            ws_protocol = "wss"
        else:
            ws_protocol = "ws"
        if self.COMFY_USER:
            ws_url_base = f"{ws_protocol}://{self.COMFY_USER}:{self.COMFY_PASSWORD}@{url_without_protocol}"
        else:
            ws_url_base = f"{ws_protocol}://{url_without_protocol}"
        return urljoin(ws_url_base, "/ws?clientId={}")

    @computed_field
    @property
    def all_cors(self) -> list[str]:
        return [str(s).rstrip('/') for s in self.BACKEND_CORS_ORIGINS] + [self.FRONTEND_HOST]
    
    @computed_field
    @property
    def is_production(self) -> bool:
        return self.RUN_ENV == "PRODUCTION"

    @computed_field
    @property
    def DATABASE_URL(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )
    
    @computed_field
    @property
    def ASYNC_DATABASE_URL(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.POSTGRES_USER,
            password=self.POSTGRES_PASSWORD,
            host=self.POSTGRES_SERVER,
            port=self.POSTGRES_PORT,
            path=self.POSTGRES_DB,
        )


settings = Settings()
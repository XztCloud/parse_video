from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/parse_video"
    REDIS_URL: str = "redis://localhost:6379/0"
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE: int = 500 * 1024 * 1024
    ALIYUN_ASR_APP_KEY: str = ""
    ALIYUN_ASR_ACCESS_KEY: str = ""
    ALIYUN_ASR_ACCESS_SECRET: str = ""
    DASHSCOPE_API_KEY: str = ""
    MAX_CONCURRENT_TASKS: int = 3
    BYTEDANCE_APP_ID: str = ""
    BYTEDANCE_TOKEN: str = ""

    class Config:
        env_file = ".env"

settings = Settings()
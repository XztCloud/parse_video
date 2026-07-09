import logging

from sqlalchemy import select, text


from app.database import SessionLocal
from app.api.security import get_password_hash
from app.models.user import User
from app.config import settings
from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed
from sqlalchemy.exc import SQLAlchemyError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

max_tries = 60 * 5  # 5 minutes
wait_seconds = 1

@retry(
    stop=stop_after_attempt(max_tries),
    wait=wait_fixed(wait_seconds),
    before=before_log(logger, logging.INFO),
    after=after_log(logger, logging.WARN),
)
def init() -> None:
    try:
        # 使用 with 语句，执行完后会自动调用 db.close()，即使中途报错也会释放连接
        with SessionLocal() as db:
            # 💡 在 SQLAlchemy 中，检测连接最标准、最轻量的做法是执行 text("SELECT 1")
            db.execute(text("SELECT 1"))
            logger.info("数据库连接测试成功，服务正常启动。")
    except Exception as e:
        # 💡 此时只是连接失败，日志应准确描述错误，方便排查
        logger.exception("数据库连接失败，请检查数据库服务是否启动或配置是否正确！")
        raise e

def main():
    logger.info("Initializing service")
    init()
    logger.info("Service finished initializing")

if __name__ == "__main__":
    main()
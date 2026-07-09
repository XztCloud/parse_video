
import logging

from app.database import SessionLocal
from app.api.security import get_password_hash
from app.models.user import User
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init():
    try:
        db=SessionLocal()
        try:
            super_admin = db.query(User).filter(User.email == settings.SUPER_ADMINI_EMAIL).first()
            logger.info('find super admin')
            if not super_admin:
                logger.info('not find super admin, create it')
                super_admin = User(
                    email=settings.SUPER_ADMINI_EMAIL, 
                    hashed_password=get_password_hash(settings.SUPER_ADMINI_PASSWORD),
                    full_name='Admin',
                    is_active=True,
                    is_superuser=True
                )
                db.add(super_admin)
                db.commit()
                db.refresh(super_admin)
                logger.info('not find super admin, create complete')
        finally:
            db.close()
    except Exception as e:
        logger.exception('创建管理员账号失败')
        raise

def main() -> None:
    logger.info("Creating initial data")
    init()
    logger.info("Initial data created")

if __name__ == "__main__":
    main()
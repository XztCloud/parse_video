from celery import Celery
from app.config import settings

celery_app = Celery("parse_video", broker=settings.REDIS_URL, backend=settings.REDIS_URL)
celery_app.conf.update(task_serializer="json", accept_content=["json"], result_serializer="json", timezone="Asia/Shanghai", enable_utc=True)
celery_app.autodiscover_tasks(["app.tasks.parse_video"], force=True)
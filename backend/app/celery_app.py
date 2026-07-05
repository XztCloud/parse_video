import os
import sys

from celery import Celery
from app.config import settings

celery_app = Celery(
    "parse_video", 
    broker=settings.REDIS_URL, 
    backend=settings.REDIS_URL,
    include=["app.tasks.parse_video"] 
)
celery_app.conf.update(
    task_serializer="json", 
    accept_content=["json"], 
    result_serializer="json", 
    timezone="Asia/Shanghai", 
    enable_utc=True,
    worker_redirect_stdouts=False,
    worker_redirect_stdouts_level='DEBUG'
)
celery_app.autodiscover_tasks(["app.tasks.parse_video"], force=True)



def start_celery_worker():
    """供 pyproject.toml 绑定的命令入口函数"""
    print("🚀 正在通过 Poetry 快捷命令启动 Celery Worker...")
    
    try:
        log_file = os.path.join(settings.LOG_DIR, "celery.log")

        worker = celery_app.Worker(
            loglevel="INFO",
            pool="solo",
            logfile=log_file,  # ✨ 核心：指定了这个参数，Celery 就会自动写文件
        )
        
        print(f"ℹ️ Celery 自带日志将自动写入到: {log_file}")
        worker.start()
    except Exception as e:
        
        print(f"❌ Worker 异常退出: {e}")
        sys.exit(1)

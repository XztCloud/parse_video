


import asyncio
from contextlib import asynccontextmanager
import threading

from app.config import settings
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine, AsyncSession

class ProcessLoopManager:
    """保证当前进程内有且仅有一个常驻 Event Loop 的管理器
    """
    def __init__(self):
        self.loop = None
        self.thread = None
        self.async_engine = None
        self.AsyncSessionLocal = None
        
    def init_process(self):
        if self.loop is not None and not self.loop.is_closed():
            return
        
        self.loop = asyncio.new_event_loop()
        
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        
        future = asyncio.run_coroutine_threadsafe(self._init_db(), self.loop)
        future.result()
        
        
    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever() # 保持进程内 loop 永远在后台
        
    async def _init_db(self):
        self.async_engine = create_async_engine(
            str(settings.ASYNC_DATABASE_URL),
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20
        )
        self.AsyncSessionLocal = async_sessionmaker(
            bind=self.async_engine,
            expire_on_commit=False,
            autoflush=False,
        )
        
    def run(self, coro):
        """线程安全地向进程唯一的 Loop 提交协程任务"""
        future = asyncio.run_coroutine_threadsafe(coro, self.loop)
        return future.result()

    def shutdown(self):
        if self.loop and self.async_engine:
            asyncio.run_coroutine_threadsafe(self.async_engine.dispose(), self.loop).result()
            self.loop.call_soon_threadsafe(self.loop.stop)
            
# 全局进程级单例
process_loop = ProcessLoopManager()



    
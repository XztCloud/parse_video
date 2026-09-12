from typing import List

from sqlalchemy import ARRAY, Column, ForeignKey, Integer, String, Text, DateTime
from ..database import Base
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Novel(Base):
    """小说模型 - 存储上传的小说信息"""
    __tablename__ = "novels"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False, comment="小说标题")
    file_path = Column(Text, nullable=False, comment="novel file path on disk")
    raw_content = Column(Text, nullable=True, comment="full novel text")
    chapter_count = Column(Integer, nullable=True, comment="detected chapter count")
    status = Column(String(32), nullable=False, default="PENDING", comment="PENDING/PROCESSING/DONE/FAILED")
    error_message = Column(Text, nullable=True)
    progress = Column(Integer, default=0, comment="处理进度 0-100")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return f"<Novel(id={self.id}, title='{self.title}', status='{self.status}')>"
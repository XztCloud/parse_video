from sqlalchemy import Column, String, Integer, Float, DateTime, Enum
from sqlalchemy.orm import relationship
from ..database import Base
import enum
from datetime import datetime

class VideoSource(enum.Enum):
    LOCAL = "local"
    DOUYIN = "douyin"

class VideoStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    source_type = Column(Enum(VideoSource), default=VideoSource.LOCAL)
    source_url = Column(String(1024), nullable=True)
    file_path = Column(String(512), nullable=False)
    duration = Column(Float, nullable=True)
    status = Column(Enum(VideoStatus), default=VideoStatus.PENDING)
    progress = Column(Integer, default=0)
    error_message = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    script = relationship("Script", back_populates="video", uselist=False)
from sqlalchemy import Column, String, Integer, Float, DateTime, Enum, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from ..database import Base
import enum
from datetime import datetime

class VideoSource(enum.Enum):
    LOCAL = "local"
    DOUYIN = "douyin"

class VideoStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"

class Video(Base):
    __tablename__ = "videos"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    source_type = Column(Enum(VideoSource, name="videosource", create_type=True), default=VideoSource.LOCAL)
    source_url = Column(String(1024), nullable=True)
    file_path = Column(String(512), nullable=False)
    duration = Column(Float, nullable=True)
    category = Column(String(64), nullable=True, comment="视频类型（对应前端 tagPresets 类型名）")
    type_summary = Column(Text, nullable=True, comment="视频一句话总结")
    status = Column(Enum(VideoStatus, name="videostatus", create_type=True), default=VideoStatus.PENDING)
    progress = Column(Integer, default=0)
    error_message = Column(String(1024), nullable=True)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        comment="归属用户；删除用户时级联删除其视频",
    )
    created_at = Column(DateTime, default=datetime.utcnow)
    script = relationship("Script", back_populates="video", uselist=False, cascade="all, delete-orphan")

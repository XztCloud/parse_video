from sqlalchemy import Column, String, Integer, Float, DateTime, Enum, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from ..database import Base
from datetime import datetime
import enum

class SegmentType(enum.Enum):
    SHOT = "shot"
    DIALOGUE = "dialogue"
    MIXED = "mixed"

class Script(Base):
    __tablename__ = "scripts"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id"), unique=True)
    content = Column(JSON, nullable=True)
    raw_asr_text = Column(Text, nullable=True)
    raw_visual_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    video = relationship("Video", back_populates="script")
    segments = relationship("ScriptSegment", back_populates="script", cascade="all, delete-orphan")

class ScriptSegment(Base):
    __tablename__ = "script_segments"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("scripts.id"))
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    shot_description = Column(Text, nullable=True)
    dialogue = Column(JSON, nullable=True)
    segment_type = Column(Enum(SegmentType), default=SegmentType.MIXED)
    script = relationship("Script", back_populates="segments")
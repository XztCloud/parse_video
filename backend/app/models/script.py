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
    parse_pointer = Column(Text, nullable=True, comment="解析重点信息")
    parse_script = Column(JSON, nullable=True, comment="解析剧本脚本")
    parse_file_path = Column(Text, nullable=True, comment="解析结果文件路径,markdown格式")
    content = Column(JSON, nullable=True, comment="完整剧本内容，包含分镜、台词等信息")
    raw_asr_text = Column(Text, nullable=True)
    raw_visual_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    video = relationship("Video", back_populates="script")
    segments = relationship("ScriptSegment", back_populates="script", cascade="all, delete-orphan")
    clone_script = relationship("CloneScript", back_populates="script", cascade="all, delete-orphan")

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

class CloneScript(Base):
    __tablename__ = "clone_scripts"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("scripts.id"))
    clone_theme = Column(String(255), nullable=True, comment="复刻视频标题")
    clone_parse_pointer = Column(JSON, nullable=True, comment="复刻解析重点信息")
    clone_parse_script = Column(JSON, nullable=True, comment="复刻解析剧本脚本")
    clone_parse_file_path = Column(Text, nullable=True, comment="复刻解析结果文件路径,markdown格式")
    clone_content = Column(JSON, nullable=True, comment="复刻完整剧本内容，包含分镜、台词等信息")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    script = relationship("Script", back_populates="clone_script")
    clone_segments = relationship("CloneScriptSegment", back_populates="clone_script", cascade="all, delete-orphan")
    clone_videos = relationship("CloneVideo", back_populates="clone_script", cascade="all, delete-orphan")


class CloneScriptSegment(Base):
    __tablename__ = "clone_script_segments"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("clone_scripts.id"))
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    shot_description = Column(Text, nullable=True)
    dialogue = Column(JSON, nullable=True)
    segment_type = Column(Enum(SegmentType), default=SegmentType.MIXED)
    clone_script = relationship("CloneScript", back_populates="clone_segments")
    
class CloneVideo(Base):
    __tablename__ = "clone_videos"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("clone_scripts.id"), unique=True)
    file_path = Column(String(512), nullable=False)
    duration = Column(Float, nullable=True)
    error_message = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    clone_script = relationship("CloneScript", back_populates="clone_videos")

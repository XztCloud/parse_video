from sqlalchemy import Column, Index, String, Integer, Float, DateTime, Enum, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from ..database import Base
from datetime import datetime
import enum

class SegmentType(enum.Enum):
    SHOT = "shot"
    DIALOGUE = "dialogue"
    MIXED = "mixed"

class CloneStatus(enum.Enum):
    PENDING = "PENDING"
    PLOT = "PLOT"
    PLOT_DONE = "PLOT_DONE"
    VOICE = "VOICE"
    VOICE_DONE = "VOICE_DONE"
    SEGMENTS = "SEGMENTS"
    SEGMENTS_DONE = "SEGMENTS_DONE"
    IMAGE = "IMAGE"
    IMAGE_DONE = "IMAGE_DONE"
    VIDEO = "VIDEO"
    DONE = "DONE"
    FAILED = "FAILED"

class Script(Base):
    __tablename__ = "scripts"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("videos.id", ondelete="CASCADE"), unique=True)
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
    script_id = Column(Integer, ForeignKey("scripts.id", ondelete="CASCADE"))
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    shot_description = Column(Text, nullable=True)
    dialogue = Column(JSON, nullable=True)
    segment_type = Column(Enum(SegmentType), default=SegmentType.MIXED)
    script = relationship("Script", back_populates="segments")

class CloneScript(Base):
    __tablename__ = "clone_scripts"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("scripts.id", ondelete="CASCADE"))
    clone_theme = Column(String(255), comment="复刻视频主题")
    clone_requirements = Column(JSON, nullable=True, comment="复刻视频的要求")
    clone_parse_pointer = Column(JSON, nullable=True, comment="复刻剧本解析")
    clone_parse_file_path = Column(Text, nullable=True, comment="复刻解析结果文件路径,markdown格式")
    clone_status = Column(Enum(CloneStatus), default=CloneStatus.PENDING)
    clone_progress = Column(Integer, default=0)
    clone_error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    script = relationship("Script", back_populates="clone_script")
    clone_segments = relationship("CloneScriptSegment", back_populates="clone_script", cascade="all, delete-orphan")
    clone_videos = relationship("CloneVideo", back_populates="clone_script", cascade="all, delete-orphan")
    clone_voices = relationship("CloneVoice", back_populates="clone_script", cascade="all, delete-orphan")
    clone_images = relationship("CloneImage", back_populates="clone_script", cascade="all, delete-orphan")

class CloneVoice(Base):
    __tablename__ = "clone_voices"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("clone_scripts.id", ondelete="CASCADE"))
    role_name = Column(String(128), nullable=False, index=True)
    duration = Column(Float, nullable=False)
    voice_type = Column(String(256), nullable=True, comment="声音风格")
    spk_id = Column(Text, nullable=False)
    path = Column(Text, nullable=False)
    text = Column(Text, nullable=False)
    text_md5 = Column(String(32), nullable=False)
    sort_order = Column(Integer, default=0, comment="排序序号")
    clone_script = relationship("CloneScript", back_populates="clone_voices")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index('ix_role_md5_type', 'role_name', 'text_md5', 'voice_type'),
    )


class CloneImage(Base):
    __tablename__ = "clone_images"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("clone_scripts.id", ondelete="CASCADE"))
    role_name = Column(String(128), nullable=False, index=True)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    path = Column(String(256), nullable=False)
    prompt = Column(Text, nullable=True)
    desc = Column(String(128), nullable=True)
    clone_script = relationship("CloneScript", back_populates="clone_images")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
class CloneScriptSegment(Base):
    __tablename__ = "clone_script_segments"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("clone_scripts.id", ondelete="CASCADE"))
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    shot_description = Column(Text, nullable=True)
    dialogue = Column(JSON, nullable=True)
    first_frame_path = Column(String(256), nullable=True)
    segment_type = Column(String(128), nullable=True)
    clone_script = relationship("CloneScript", back_populates="clone_segments")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
class CloneVideo(Base):
    __tablename__ = "clone_videos"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("clone_scripts.id", ondelete="CASCADE"))
    file_path = Column(String(512), nullable=False)
    duration = Column(Float, nullable=True)
    error_message = Column(String(1024), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    clone_script = relationship("CloneScript", back_populates="clone_videos")

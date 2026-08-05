from sqlalchemy import BigInteger, Column, Index, String, Integer, Float, DateTime, Enum, ForeignKey, JSON, Text
from sqlalchemy.orm import relationship
from ..database import Base
from datetime import datetime
import enum

class SegmentType(str, enum.Enum):
    SHOT = "shot"
    DIALOGUE = "dialogue"
    MIXED = "mixed"

class SegmentImageType(str, enum.Enum):
    FIRST_FRAME = "FIRST_FRAME"
    LAST_FRAME = "LAST_FRAME"
    
class GenerateStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"

class CloneStatus(str, enum.Enum):
    PENDING = "PENDING"
    PLOT = "PLOT"
    PLOT_DONE = "PLOT_DONE"
    VOICE = "VOICE"
    VOICE_DONE = "VOICE_DONE"
    SEGMENTS = "SEGMENTS"
    SEGMENTS_DONE = "SEGMENTS_DONE"
    IMAGE = "IMAGE"
    IMAGE_DONE = "IMAGE_DONE"
    FRAME = 'FRAME'
    FRAME_DONE = 'FRAME_DONE'
    SEGMENT_VIDEO = "SEGMENT_VIDEO"
    SEGMENT_VIDEO_DONE = "SEGMENT_VIDEO_DONE"
    MERGE_VIDEO = "MERGE_VIDEO"
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
    segment_type = Column(Enum(SegmentType, name="segmenttype", create_type=True), default=SegmentType.MIXED)
    script = relationship("Script", back_populates="segments")

class CloneScript(Base):
    __tablename__ = "clone_scripts"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("scripts.id", ondelete="CASCADE"))
    clone_theme = Column(String(255), comment="复刻视频主题")
    clone_requirements = Column(JSON, nullable=True, comment="复刻视频的要求")
    clone_parse_pointer = Column(JSON, nullable=True, comment="复刻剧本解析")
    clone_parse_file_path = Column(Text, nullable=True, comment="复刻解析结果文件路径,markdown格式")
    clone_status = Column(Enum(CloneStatus, name="clonestatus", create_type=True), default=CloneStatus.PENDING)
    clone_progress = Column(Integer, default=0)
    clone_error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    script = relationship("Script", back_populates="clone_script")
    clone_segments = relationship("CloneScriptSegment", back_populates="clone_script", cascade="all, delete-orphan")
    clone_videos = relationship("CloneVideo", back_populates="clone_script", cascade="all, delete-orphan")
    clone_voices = relationship("CloneVoice", back_populates="clone_script", cascade="all, delete-orphan")
    clone_role_images = relationship("CloneRoleImage", back_populates="clone_script", cascade="all, delete-orphan")
    clone_scene_images = relationship("CloneSceneImage", back_populates="clone_script", cascade="all, delete-orphan")

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
    # 声明这是一个抽象基类，告诉 SQLAlchemy 不要为它建表
    __abstract__ = True  
    id = Column(Integer, primary_key=True, index=True)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    path = Column(String(256), nullable=False)
    prompt = Column(Text, nullable=True)
    status = Column(
        Enum(GenerateStatus, name="generatestatus", create_type=True), 
        nullable=True,
        default=GenerateStatus.PENDING, 
        comment="重新生成图片人物状态"
    )
    seed = Column(BigInteger, nullable=True, comment="生图 Seed")
    desc = Column(String(128), nullable=True,  comment="前端展示描述信息，例如肖像、场景、首帧、尾帧")
    version = Column(Integer, nullable=False, comment="图片版本")
    name_comfy = Column(String(128), nullable=True, comment="图片再comfy中名称，用于图生图、图生视频")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class CloneRoleImage(CloneImage):
    __tablename__ = "clone_role_images"
    script_id = Column(Integer, ForeignKey("clone_scripts.id", ondelete="CASCADE"))
    role_name = Column(String(128), nullable=False, index=True)
    clone_script = relationship("CloneScript", back_populates="clone_role_images")
    faceless = Column(Text, nullable=True)
    
class CloneSceneImage(CloneImage):
    __tablename__ = "clone_scene_images"
    script_id = Column(Integer, ForeignKey("clone_scripts.id", ondelete="CASCADE"))
    scene_name = Column(String(128), nullable=False, index=True)
    clone_script = relationship("CloneScript", back_populates="clone_scene_images")

class CloneScriptSegment(Base):
    __tablename__ = "clone_script_segments"
    id = Column(Integer, primary_key=True, index=True)
    script_id = Column(Integer, ForeignKey("clone_scripts.id", ondelete="CASCADE"))
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    shot_description = Column(Text, nullable=True, comment="分镜描述提示词")
    dialogue = Column(JSON, nullable=True, comment="分镜对话")
    role_view_info = Column(JSON, nullable=True, comment="分镜角色视觉描述")
    scene_name = Column(String(256),comment="场景名")
    shot_type = Column(String(128), comment="镜头描述")
    segment_type = Column(String(128), nullable=True, comment="分镜整体情绪")
    clone_script = relationship("CloneScript", back_populates="clone_segments")
    clone_segment_images = relationship("CloneSegmentImg", back_populates="clone_script_segment", cascade="all, delete-orphan")
    clone_segment_video = relationship("CloneSegmentVideo", back_populates="clone_script_segment", cascade="all, delete-orphan")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
class CloneSegmentImg(CloneImage):
    __tablename__ = "clone_segment_images"
    clone_script_sgement_id = Column(Integer, ForeignKey("clone_script_segments.id", ondelete="CASCADE"))
    clone_segment_image_type = Column(
        Enum(SegmentImageType, name="segmentimagetype", create_type=True), 
        default=SegmentImageType.FIRST_FRAME
    )
    clone_script_segment = relationship("CloneScriptSegment", back_populates="clone_segment_images")

class CloneSegmentVideo(Base):
    __tablename__ = "clone_segment_video"
    id = Column(Integer, primary_key=True, index=True)
    clone_script_sgement_id = Column(Integer, ForeignKey("clone_script_segments.id", ondelete="CASCADE"))
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    path = Column(String(256), nullable=False)
    prompt = Column(Text, nullable=True)
    status = Column(
        Enum(GenerateStatus, name="generatestatus", create_type=False), 
        nullable=False,
        default=GenerateStatus.PENDING, 
        comment="重新生成视频状态"
    )
    seed = Column(BigInteger, nullable=True, comment="生图 Seed")
    desc = Column(String(128), nullable=True,  comment="前端展示描述信息")
    version = Column(Integer, nullable=False, default=0, comment="图片版本")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    clone_script_segment = relationship("CloneScriptSegment", back_populates="clone_segment_video")
    
class CloneVideo(Base):
    __tablename__ = "clone_videos"
    id = Column(Integer, primary_key=True, index=True)
    video_id = Column(Integer, ForeignKey("clone_scripts.id", ondelete="CASCADE"))
    file_path = Column(String(512), nullable=False)
    duration = Column(Float, nullable=True)
    version = Column(Integer, default=0)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    rate = Column(Integer, default=24)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    clone_script = relationship("CloneScript", back_populates="clone_videos")

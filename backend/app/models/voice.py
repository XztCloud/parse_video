

from sqlalchemy import Column, Float, Integer, String, Text

from app.database import Base
from pydantic import Field


class VoiceInfoCollect(Base):
    __tablename__ = "voice"
    id = Column(Integer, primary_key=True, index=True)
    spk_id: str = Column(String(255), nullable=False, index=True, comment="音色id")
    text: str = Column(Text, nullable=False, comment="音频文本")
    char_count: int = Column(Integer, nullable=False, comment="文本总字数")
    punc_count: int = Column(Integer, nullable=False, comment="标点符号数量")
    audio_duration: float = Column(Float, nullable=False)
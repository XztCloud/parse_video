from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class ScriptSegmentOut(BaseModel):
    id: int
    start_time: float
    end_time: float
    shot_description: Optional[str] = None
    dialogue: Optional[str] = None
    segment_type: str
    class Config:
        from_attributes = True

class ScriptSegmentUpdate(BaseModel):
    shot_description: Optional[str] = None
    dialogue: Optional[str] = None

class ScriptDetail(BaseModel):
    id: int
    video_id: int
    content: Optional[dict] = None
    raw_asr_text: Optional[str] = None
    raw_visual_text: Optional[str] = None
    segments: List[ScriptSegmentOut] = []
    created_at: datetime
    updated_at: datetime
    class Config:
        from_attributes = True
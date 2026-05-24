from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class VideoUploadResponse(BaseModel):
    id: int
    title: str
    source_type: str
    status: str
    created_at: datetime
    class Config:
        from_attributes = True

class VideoDetail(VideoUploadResponse):
    duration: Optional[float] = None
    progress: int = 0
    error_message: Optional[str] = None

class DouyinParseRequest(BaseModel):
    url: str
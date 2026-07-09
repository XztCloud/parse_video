

from datetime import datetime
import uuid

from pydantic import BaseModel
from sqlalchemy import UUID, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        index=True,)
    email = Column(String(128), nullable=False, index=True, unique=True)
    hashed_password = Column(String(256), nullable=False)
    full_name = Column(String(256), nullable=True)
    is_active = Column(Boolean, default=False)
    is_superuser = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class TokenPayload(BaseModel):
    sub: str | None = None
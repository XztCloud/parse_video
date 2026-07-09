

from datetime import datetime
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.api.deps import SessionDep
from app.api.security import get_password_hash
from app.models.user import User


router = APIRouter(prefix="/users", tags=["users"])

class UserBase(BaseModel):
    email: EmailStr = Field(max_length=255)
    full_name: str | None = Field(default=None, max_length=255)

class UserCreate(UserBase):
    password: str = Field(min_length=8, max_length=128)

class UserPublic(UserBase):
    id: uuid.UUID
    created_at: datetime | None = None

@router.post("", response_model=UserPublic)
async def create_user(db: SessionDep, user_create: UserCreate):
    user = db.query(User).filter(User.email == user_create.email).first()
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system."
        )
    hashed_password = get_password_hash(user_create.password)
    kwargs = {k: v for k, v in user_create.model_dump().items() if k in User.__table__.columns}
    new_user = User(**kwargs, hashed_password=hashed_password)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    print(f'new_user: {vars(new_user)}')
    kwargs = {k: v for k, v in vars(new_user).items() if k in UserPublic.model_fields.keys()}

    print(f'new kwargs: {kwargs}')
    return UserPublic.model_validate(kwargs)


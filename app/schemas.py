from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr
    username: str

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

class JournalEntryBase(BaseModel):
    title: str
    content: str

class JournalEntryCreate(JournalEntryBase):
    pass

class JournalEntryResponse(JournalEntryBase):
    id: int
    sentiment_score: Optional[float] = None
    sentiment_label: Optional[str] = None
    created_at: datetime
    user_id: int

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str
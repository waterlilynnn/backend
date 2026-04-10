from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class StaffCreate(BaseModel):
    full_name: str
    email: EmailStr

class UserResponse(BaseModel):
    id: int
    username: str
    full_name: str
    email: EmailStr
    role: str 
    is_active: bool
    created_at: datetime
    temporary_password: Optional[str] = None

    class Config:
        from_attributes = True

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
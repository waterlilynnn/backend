from pydantic import BaseModel, EmailStr
from typing import Optional
from app.schemas.user import StaffCreate as StaffCreateRequest

class StaffResponse(BaseModel):
    id: int
    full_name: str
    email: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True
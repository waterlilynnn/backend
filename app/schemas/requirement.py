from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class HaulerRequirementBase(BaseModel):
    hauler_type: str
    requirement_name: str
    description: Optional[str] = None
    is_required: bool = True
    sort_order: int = 0

class HaulerRequirementCreate(HaulerRequirementBase):
    pass

class HaulerRequirementUpdate(BaseModel):
    hauler_type: Optional[str] = None
    requirement_name: Optional[str] = None
    description: Optional[str] = None
    is_required: Optional[bool] = None
    sort_order: Optional[int] = None

class HaulerRequirementResponse(HaulerRequirementBase):
    id: int
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class BusinessRequirementUpdate(BaseModel):
    is_completed: Optional[bool] = None
    notes: Optional[str] = None

class BusinessRequirementResponse(BaseModel):
    id: int
    business_id: int
    requirement_id: int
    is_completed: bool
    completed_date: Optional[datetime]
    notes: Optional[str]
    completed_by: Optional[str]
    
    requirement_name: str
    description: Optional[str]
    is_required: bool
    
    class Config:
        from_attributes = True
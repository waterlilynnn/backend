from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime

class RequirementChecklistCreate(BaseModel):
    dti_registration: bool = False
    mayor_permit: bool = False
    occupancy_permit: bool = False
    sanitation_permit: bool = False
    fire_safety_cert: bool = False
    environmental_compliance: bool = False
    additional_documents: Optional[Dict[str, Any]] = None

class RequirementChecklistUpdate(BaseModel):
    dti_registration: Optional[bool] = None
    mayor_permit: Optional[bool] = None
    occupancy_permit: Optional[bool] = None
    sanitation_permit: Optional[bool] = None
    fire_safety_cert: Optional[bool] = None
    environmental_compliance: Optional[bool] = None
    additional_documents: Optional[Dict[str, Any]] = None

class RequirementChecklistResponse(BaseModel):
    id: int
    business_record_id: int
    dti_registration: bool
    mayor_permit: bool
    occupancy_permit: bool
    sanitation_permit: bool
    fire_safety_cert: bool
    environmental_compliance: bool
    additional_documents: Optional[Dict[str, Any]]
    submitted_at: Optional[datetime]
    last_updated_at: Optional[datetime]

    class Config:
        from_attributes = True
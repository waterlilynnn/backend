from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime, date
from enum import Enum

class HaulerType(str, Enum):
    CITY = "City"
    BARANGAY = "Barangay"
    ACCREDITED = "Accredited"
    HAZARDOUS = "Hazardous"
    EXEMPTED = "Exempted"
    NO_CONTRACT = "No Contract"

class ApplicationType(str, Enum):
    NEW = "NEW"
    RENEWAL = "RENEWAL"

class BusinessCreate(BaseModel):
    bin_number: Optional[str] = None
    establishment_name: str
    business_line: str
    
    owner_last_name: str
    owner_first_name: str
    owner_middle_name: Optional[str] = None
    owner_suffix: Optional[str] = None
    
    contact_number: Optional[str] = None
    email: Optional[EmailStr] = None
    
    location: str  # Required
    has_own_structure: bool = False
    
    hauler_type: HaulerType
    application_type: ApplicationType = ApplicationType.NEW
    
    @field_validator('owner_last_name', 'owner_first_name')
    def validate_name(cls, v):
        if not v or not v.strip():
            raise ValueError('Name field is required')
        if any(char.isdigit() for char in v):
            raise ValueError('Name cannot contain numbers')
        return v.strip().upper()

class BusinessUpdate(BaseModel):
    # Business Information
    bin_number: Optional[str] = None
    establishment_name: Optional[str] = None
    business_line: Optional[str] = None
    
    # Owner Information
    owner_last_name: Optional[str] = None
    owner_first_name: Optional[str] = None
    owner_middle_name: Optional[str] = None
    owner_suffix: Optional[str] = None
    
    # Contact
    contact_number: Optional[str] = None
    email: Optional[EmailStr] = None
    
    # Location & Structure
    location: Optional[str] = None
    has_own_structure: Optional[bool] = None
    
    # Classification
    hauler_type: Optional[HaulerType] = None
    
    # Application Details
    application_type: Optional[ApplicationType] = None
    application_date: Optional[datetime] = None
    
    # Clearance Info
    control_number: Optional[str] = None
    date_issued: Optional[date] = None
    validity: Optional[date] = None
    sticker_color: Optional[str] = None
    
    # Status
    status: Optional[str] = None
    
    # Violation
    has_violation: Optional[bool] = None
    violation_details: Optional[str] = None
    violation_status: Optional[str] = None
    
    # Revocation
    is_revoked: Optional[bool] = None
    revoked_reason: Optional[str] = None

class BusinessResponse(BaseModel):
    id: int
    bin_number: Optional[str]
    establishment_name: str
    business_line: str
    
    owner_last_name: Optional[str] 
    owner_first_name: Optional[str] 
    owner_middle_name: Optional[str]
    owner_suffix: Optional[str]
    owner_name_raw: Optional[str]    
    
    contact_number: Optional[str]
    email: Optional[str]
    
    location: Optional[str]        
    has_own_structure: Optional[bool] = False 
    
    hauler_type: str
    application_type: str
    status: str
    
    control_number: Optional[str]
    date_issued: Optional[date]
    validity: Optional[date]
    sticker_color: Optional[str]
    
    has_violation: bool
    violation_status: str
    
    is_revoked: bool
    
    created_at: datetime
    created_by: int
    approved_at: Optional[datetime]
    
    completed_requirements: Optional[int] = 0
    total_requirements: Optional[int] = 0
    
    class Config:
        from_attributes = True

class BusinessSearchResponse(BaseModel):
    id: int
    establishment_name: str
    owner_name: str
    bin_number: Optional[str]
    location: Optional[str]  
    hauler_type: str
    status: str
    control_number: Optional[str]
    has_violation: bool
    
    class Config:
        from_attributes = True

class BusinessListResponse(BaseModel):
    total: int
    items: List[BusinessSearchResponse]
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class ClearanceGenerateRequest(BaseModel):
    application_id: int

class ClearanceResponse(BaseModel):
    id: int
    application_id: int
    control_number: str
    clearance_color: str
    valid_until: datetime
    printed_by: int
    printed_at: datetime
    is_printed: bool
    is_claimed: bool
    
    class Config:
        from_attributes = True

class ClearancePrintData(BaseModel):
    """Data para sa PDF generation"""
    # Clearance header
    control_number: str
    clearance_color: str
    issued_date: str
    valid_until: str
    
    # Business info
    establishment_name: str
    owner_name: str
    business_address: str
    barangay: str
    hauler_type: str
    business_line: str
    
    # Issuance info
    issued_by: str
    issued_by_position: str = "Staff"
    
    class Config:
        from_attributes = True
from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClearanceGenerateRequest(BaseModel):
    business_record_id: int 


class ClearanceResponse(BaseModel):
    id: int
    business_record_id: int   
    control_number: str
    clearance_color: str
    valid_until: datetime
    printed_by: int
    printed_at: datetime
    is_claimed: bool           
    print_count: int

    class Config:
        from_attributes = True


class ClearancePrintData(BaseModel):
    control_number: str
    clearance_color: str
    issued_date: str
    valid_until: str

    establishment_name: str
    owner_name: str
    business_address: str
    barangay: str
    hauler_type: str
    business_line: str

    issued_by: str
    issued_by_position: str = "Staff"

    # Signatories 
    recommending_name:  str = ""
    recommending_title: str = ""
    approving_name:     str = ""
    approving_title:    str = ""

    class Config:
        from_attributes = True
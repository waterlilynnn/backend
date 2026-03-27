from pydantic import BaseModel, field_validator
from typing import Optional, List
import json

class SettingUpdate(BaseModel):
    value: str
    label: Optional[str] = None

class SettingResponse(BaseModel):
    id: int
    key: str
    value: Optional[str]
    label: Optional[str]
    category: str
    is_active: bool
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True

class BinFormat(BaseModel):
    id: str
    segments: List[int]
    label: str
    is_active: bool = True

    @field_validator("segments")
    @classmethod
    def segments_must_be_positive(cls, v):
        if not v or any(s <= 0 for s in v):
            raise ValueError("Each segment must have at least 1 digit")
        if len(v) < 2:
            raise ValueError("BIN format must have at least 2 segments")
        return v

class BinFormatsPayload(BaseModel):
    formats: List[BinFormat]

class RequirementTemplateCreate(BaseModel):
    label: str
    description: Optional[str] = None
    is_required: bool = True
    sort_order: int = 0
    hauler_type: Optional[str] = None

    @field_validator("label")
    @classmethod
    def label_not_empty(cls, v):
        if not v or not v.strip():
            raise ValueError("Label cannot be empty")
        return v.strip()

class RequirementTemplateUpdate(BaseModel):
    label: Optional[str] = None
    description: Optional[str] = None
    is_required: Optional[bool] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None
    hauler_type: Optional[str] = None

class RequirementTemplateResponse(BaseModel):
    id: int
    label: str
    description: Optional[str]
    is_required: bool
    sort_order: int
    is_active: bool
    hauler_type: Optional[str]

    class Config:
        from_attributes = True

class SubmissionToggle(BaseModel):
    is_submitted: bool
    notes: Optional[str] = None

class SubmissionResponse(BaseModel):
    id: int
    template_id: int
    label: str
    is_required: bool
    hauler_type: Optional[str]
    is_submitted: bool
    submitted_at: Optional[str] = None
    notes: Optional[str] = None

    class Config:
        from_attributes = True

class BusinessRequirementsResponse(BaseModel):
    business_id: int
    hauler_type: Optional[str]
    total: int
    submitted: int
    pending: int
    items: List[SubmissionResponse]
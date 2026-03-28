from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
import json
from datetime import datetime

from app.core.database import get_db
from app.core.security import admin_only, staff_only, log_audit
from app.models.user import User
from app.models.setting import SystemSetting
from app.models.requirement import RequirementTemplate, RequirementSubmission
from app.models.business_record import BusinessRecord
from app.schemas.setting import (
    SettingResponse, SettingUpdate,
    BinFormatsPayload, BinFormat,
    RequirementTemplateCreate, RequirementTemplateUpdate, RequirementTemplateResponse,
)

router = APIRouter(prefix="/admin/settings", tags=["Admin Settings"])


DEFAULT_BIN_FORMATS = [
    {"id": "fmt_1", "segments": [7, 4, 7],    "label": "7-4-7  (e.g. 0402119-2011-0000466)",    "is_active": True},
    {"id": "fmt_2", "segments": [3, 2, 4, 7], "label": "3-2-4-7 (e.g. 129-00-2025-0000197)", "is_active": True},
]

# Helpers
def _get_or_create_setting(db: Session, key: str, default_value: str, label: str, category: str) -> SystemSetting:
    setting = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not setting:
        setting = SystemSetting(key=key, value=default_value, label=label, category=category)
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


# BIN Formats — public read (no auth needed so the business form can fetch it*babaguhin)
@router.get("/bin-formats/public", tags=["Admin Settings"])
def get_bin_formats_public(db: Session = Depends(get_db)):
    """Return active BIN formats. No auth required — used by the business form."""
    setting = _get_or_create_setting(
        db, "bin_formats", json.dumps(DEFAULT_BIN_FORMATS), "BIN Number Formats", "validation"
    )
    raw = json.loads(setting.value)
    return [f for f in raw if f.get("is_active", True)]


@router.get("/bin-formats", response_model=List[BinFormat])
def get_bin_formats(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    setting = _get_or_create_setting(
        db, "bin_formats", json.dumps(DEFAULT_BIN_FORMATS), "BIN Number Formats", "validation"
    )
    raw = json.loads(setting.value)
    return [BinFormat(**f) for f in raw]


@router.put("/bin-formats", response_model=List[BinFormat])
def update_bin_formats(
    payload: BinFormatsPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    if not payload.formats:
        raise HTTPException(400, "At least one BIN format is required")

    setting = db.query(SystemSetting).filter(SystemSetting.key == "bin_formats").first()
    if not setting:
        setting = SystemSetting(key="bin_formats", label="BIN Number Formats", category="validation")
        db.add(setting)

    setting.value      = json.dumps([f.model_dump() for f in payload.formats])
    setting.updated_by = current_user.id
    setting.updated_at = datetime.utcnow()
    db.commit()

    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "bin_formats"})
    return payload.formats


# Requirements Templates
@router.get("/requirements", response_model=List[RequirementTemplateResponse])
def list_requirement_templates(
    include_inactive: bool = False,
    hauler_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Get all requirement templates with proper ordering"""
    q = db.query(RequirementTemplate)
    
    if not include_inactive:
        q = q.filter(RequirementTemplate.is_active == True)
    
    # Filter by hauler_type if specified
    if hauler_type:
        q = q.filter(
            (RequirementTemplate.hauler_type == None) |
            (RequirementTemplate.hauler_type == hauler_type)
        )
    
    # Order by sort_order
    return q.order_by(
        RequirementTemplate.sort_order,
        RequirementTemplate.id
    ).all()


@router.post("/requirements", response_model=RequirementTemplateResponse, status_code=201)
def create_requirement_template(
    data: RequirementTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    # Prevent exact duplicates
    existing = db.query(RequirementTemplate).filter(
        RequirementTemplate.label       == data.label,
        RequirementTemplate.is_active   == True,
        RequirementTemplate.hauler_type == data.hauler_type,
    ).first()
    if existing:
        scope = data.hauler_type or "global"
        raise HTTPException(400, f"Requirement '{data.label}' already exists for scope '{scope}'")

    template = RequirementTemplate(
        label=data.label,
        description=data.description,
        is_required=data.is_required,
        sort_order=data.sort_order,
        hauler_type=data.hauler_type,   
        is_active=True,
        created_by=current_user.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    # Backfill: only create submissions for businesses where this template applies
    biz_query = db.query(BusinessRecord)
    if data.hauler_type:
        biz_query = biz_query.filter(BusinessRecord.hauler_type == data.hauler_type)

    for biz in biz_query.all():
        # Avoid duplicate submissions
        exists = db.query(RequirementSubmission).filter(
            RequirementSubmission.business_id == biz.id,
            RequirementSubmission.template_id == template.id,
        ).first()
        if not exists:
            db.add(RequirementSubmission(
                business_id=biz.id,
                template_id=template.id,
                is_submitted=False,
            ))
    db.commit()

    log_audit(
        db, current_user.id, "CREATE", "REQUIREMENT_TEMPLATE",
        template.id, {"label": template.label, "hauler_type": template.hauler_type}
    )
    return template


@router.put("/requirements/{template_id}", response_model=RequirementTemplateResponse)
def update_requirement_template(
    template_id: int,
    data: RequirementTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    template = db.query(RequirementTemplate).filter(RequirementTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "Requirement template not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    template.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(template)

    log_audit(db, current_user.id, "UPDATE", "REQUIREMENT_TEMPLATE", template.id, {"label": template.label})
    return template


@router.delete("/requirements/{template_id}", status_code=204)
def delete_requirement_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Soft-delete. Existing submissions are kept for audit purposes."""
    template = db.query(RequirementTemplate).filter(RequirementTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "Requirement template not found")

    template.is_active  = False
    template.updated_at = datetime.utcnow()
    db.commit()

    log_audit(db, current_user.id, "DELETE", "REQUIREMENT_TEMPLATE", template.id, {"label": template.label})
    return None


@router.post("/requirements/reorder")
def reorder_requirements(
    order: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    for idx, template_id in enumerate(order):
        template = db.query(RequirementTemplate).filter(RequirementTemplate.id == template_id).first()
        if template:
            template.sort_order = idx + 1
    db.commit()
    return {"message": "Order updated"}

# business lines management
@router.get("/business-lines", tags=["Admin Settings"])
def get_business_lines(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Get all configured business lines"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == "business_lines").first()
    if not setting or not setting.value:
        from app.utils.constants import BUSINESS_LINES
        return {"business_lines": BUSINESS_LINES}
    
    try:
        lines = json.loads(setting.value)
        return {"business_lines": lines}
    except:
        from app.utils.constants import BUSINESS_LINES
        return {"business_lines": BUSINESS_LINES}

@router.put("/business-lines", tags=["Admin Settings"])
def update_business_lines(
    payload: dict,  # {"business_lines": ["Line1", "Line2"]}
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Update the list of business lines"""
    lines = payload.get("business_lines", [])
    if not lines:
        raise HTTPException(400, "At least one business line is required")
    
    setting = db.query(SystemSetting).filter(SystemSetting.key == "business_lines").first()
    if not setting:
        setting = SystemSetting(
            key="business_lines",
            label="Business Lines",
            category="general"
        )
        db.add(setting)
    
    setting.value = json.dumps(lines)
    setting.updated_by = current_user.id
    setting.updated_at = datetime.utcnow()
    db.commit()
    
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "business_lines"})
    return {"message": "Business lines updated", "count": len(lines)}

@router.get("/exempted-lines", tags=["Admin Settings"])
def get_exempted_business_lines(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Get business lines exempted from requirements"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == "exempted_business_lines").first()
    if not setting or not setting.value:
        return {"exempted_lines": []}
    
    try:
        lines = json.loads(setting.value)
        return {"exempted_lines": lines}
    except:
        return {"exempted_lines": []}

@router.put("/exempted-lines", tags=["Admin Settings"])
def update_exempted_business_lines(
    payload: dict,  
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Update business lines exempted from requirements"""
    lines = payload.get("exempted_lines", [])
    
    setting = db.query(SystemSetting).filter(SystemSetting.key == "exempted_business_lines").first()
    if not setting:
        setting = SystemSetting(
            key="exempted_business_lines",
            label="Exempted Business Lines",
            category="requirements"
        )
        db.add(setting)
    
    setting.value = json.dumps(lines)
    setting.updated_by = current_user.id
    setting.updated_at = datetime.utcnow()
    db.commit()
    
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "exempted_business_lines"})
    return {"message": "Exempted lines updated", "count": len(lines)}

# signaatories managemebt
@router.get("/signatories", tags=["Admin Settings"])
def get_signatories(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Get clearance signatory information"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == "signatories").first()
    if not setting or not setting.value:
        return {
            "recommending_name": "ANTONETTE NICOLE D. BAYOT",
            "recommending_title": "ENGINEER I",
            "approving_name": "OSCAR B. LAURENCIANA",
            "approving_title": "OIC-CENRO"
        }
    
    try:
        return json.loads(setting.value)
    except:
        return {
            "recommending_name": "ANTONETTE NICOLE D. BAYOT",
            "recommending_title": "ENGINEER I",
            "approving_name": "OSCAR B. LAURENCIANA",
            "approving_title": "OIC-CENRO"
        }

@router.put("/signatories", tags=["Admin Settings"])
def update_signatories(
    payload: dict,  
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """Update clearance signatory information"""
    required_fields = ["recommending_name", "recommending_title", "approving_name", "approving_title"]
    for field in required_fields:
        if field not in payload:
            raise HTTPException(400, f"Missing field: {field}")
    
    setting = db.query(SystemSetting).filter(SystemSetting.key == "signatories").first()
    if not setting:
        setting = SystemSetting(
            key="signatories",
            label="Clearance Signatories",
            category="clearance"
        )
        db.add(setting)
    
    setting.value = json.dumps({
        "recommending_name": payload["recommending_name"],
        "recommending_title": payload["recommending_title"],
        "approving_name": payload["approving_name"],
        "approving_title": payload["approving_title"]
    })
    setting.updated_by = current_user.id
    setting.updated_at = datetime.utcnow()
    db.commit()
    
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "signatories"})
    return {"message": "Signatories updated"}
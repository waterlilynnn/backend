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
    q = db.query(RequirementTemplate)
    if not include_inactive:
        q = q.filter(RequirementTemplate.is_active == True)
    if hauler_type:
        q = q.filter(
            (RequirementTemplate.hauler_type == None) |
            (RequirementTemplate.hauler_type == hauler_type)
        )
    
    return q.order_by(
        RequirementTemplate.hauler_type.nullsfirst(),
        RequirementTemplate.sort_order,
        RequirementTemplate.id
    ).all()


@router.post("/requirements", response_model=RequirementTemplateResponse, status_code=201)
def create_requirement_template(
    data: RequirementTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    # Prevent exact duplicates (same label + same hauler scope)
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
        # Specific hauler — only those businesses
        biz_query = biz_query.filter(BusinessRecord.hauler_type == data.hauler_type)
    # else: global — all businesses get it

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
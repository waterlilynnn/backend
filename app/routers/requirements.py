from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import json

from app.core.database import get_db
from app.core.security import staff_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.requirement import RequirementTemplate, RequirementSubmission
from app.models.setting import SystemSetting
from app.schemas.setting import SubmissionToggle

router = APIRouter(prefix="/requirements", tags=["Requirements"])


def _is_business_line_exempted(db: Session, business_line: str) -> bool:
    """Check if business line is in the exempted_business_lines setting."""
    if not business_line:
        return False
    setting = db.query(SystemSetting).filter(
        SystemSetting.key == "exempted_business_lines"
    ).first()
    if not setting or not setting.value:
        return False
    try:
        return business_line in json.loads(setting.value)
    except Exception:
        return False


@router.get("/business/{business_id}")
def get_business_requirements(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    business = db.query(BusinessRecord).filter(BusinessRecord.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    hauler_value = (
        business.hauler_type.value
        if hasattr(business.hauler_type, "value")
        else str(business.hauler_type)
    )

    #  exemption short-circuit
    if _is_business_line_exempted(db, business.business_line):
        return {
            "business_id":   business_id,
            "hauler_type":   hauler_value,
            "total":         0,
            "submitted":     0,
            "pending":       0,
            "is_exempted":   True,
            "items":         [],
        }

    templates = (
        db.query(RequirementTemplate)
        .filter(RequirementTemplate.is_active == True)
        .filter(
            (RequirementTemplate.hauler_type.is_(None)) |
            (RequirementTemplate.hauler_type == hauler_value)
        )
        .order_by(RequirementTemplate.sort_order, RequirementTemplate.id)
        .all()
    )

    # Get existing submissions for this business
    existing_submissions = {
        s.template_id: s
        for s in db.query(RequirementSubmission)
        .filter(RequirementSubmission.business_id == business_id)
        .all()
    }

    items = []
    for template in templates:
        if template.id in existing_submissions:
            sub = existing_submissions[template.id]
            items.append({
                "id":           sub.id,
                "template_id":  template.id,
                "label":        template.label,
                "is_required":  template.is_required,
                "hauler_type":  template.hauler_type,
                "is_submitted": sub.is_submitted,
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "notes":        sub.notes,
            })
        else:
            # Auto-create submission record
            new_sub = RequirementSubmission(
                business_id=business_id,
                template_id=template.id,
                is_submitted=False,
            )
            db.add(new_sub)
            db.flush()
            items.append({
                "id":           new_sub.id,
                "template_id":  template.id,
                "label":        template.label,
                "is_required":  template.is_required,
                "hauler_type":  template.hauler_type,
                "is_submitted": False,
                "submitted_at": None,
                "notes":        None,
            })

    db.commit()

    submitted_count = sum(1 for i in items if i["is_submitted"])

    return {
        "business_id":  business_id,
        "hauler_type":  hauler_value,
        "total":        len(items),
        "submitted":    submitted_count,
        "pending":      len(items) - submitted_count,
        "is_exempted":  False,
        "items":        items,
    }


@router.patch("/business/{business_id}/submission/{submission_id}")
def toggle_submission(
    business_id:   int,
    submission_id: int,
    data: SubmissionToggle,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    submission = (
        db.query(RequirementSubmission)
        .filter(
            RequirementSubmission.id == submission_id,
            RequirementSubmission.business_id == business_id,
        )
        .first()
    )

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    # Get template info for audit log
    template = db.query(RequirementTemplate).filter(RequirementTemplate.id == submission.template_id).first()
    business = db.query(BusinessRecord).filter(BusinessRecord.id == business_id).first()
    
    old_status = submission.is_submitted
    submission.is_submitted = data.is_submitted
    submission.submitted_at = datetime.utcnow() if data.is_submitted else None
    submission.submitted_by = current_user.id   if data.is_submitted else None
    submission.notes        = data.notes
    submission.updated_at   = datetime.utcnow()
    db.commit()

    # Log audit with proper details
    log_audit(
        db, current_user.id, "UPDATE_REQUIREMENT", "BUSINESS",
        business_id,
        {
            "submission_id": submission_id,
            "template_id": submission.template_id,
            "template_label": template.label if template else "Unknown",
            "is_submitted": data.is_submitted,
            "old_status": old_status,
            "business_name": business.establishment_name if business else "Unknown",
        },
    )

    return {"message": "Updated", "is_submitted": submission.is_submitted}
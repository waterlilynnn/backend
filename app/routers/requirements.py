from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.core.security import staff_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.requirement import RequirementTemplate, RequirementSubmission
from app.schemas.setting import SubmissionToggle

router = APIRouter(prefix="/requirements", tags=["Requirements"])


def _get_applicable_templates(db: Session, hauler_type_value: str):
    return db.query(RequirementTemplate).filter(
        RequirementTemplate.is_active == True,
        (
            (RequirementTemplate.hauler_type == None) |
            (RequirementTemplate.hauler_type == hauler_type_value)
        )
    ).order_by(
        RequirementTemplate.hauler_type.nullsfirst(),
        RequirementTemplate.sort_order,
        RequirementTemplate.id
    ).all()


@router.get("/business/{business_id}")
def get_business_requirements(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Get requirements checklist for a business with proper filtering"""
    business = db.query(BusinessRecord).filter(BusinessRecord.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    hauler_value = (
        business.hauler_type.value
        if hasattr(business.hauler_type, 'value')
        else str(business.hauler_type)
    )

    # Get all active templates (global + hauler-specific)
    templates = db.query(RequirementTemplate).filter(
        RequirementTemplate.is_active == True
    ).order_by(
        RequirementTemplate.sort_order,
        RequirementTemplate.id
    ).all()
    
    # Filter templates applicable to this hauler
    applicable_templates = []
    for template in templates:
        if template.hauler_type is None or template.hauler_type == hauler_value:
            applicable_templates.append(template)

    # Get existing submissions
    existing_submissions = {
        s.template_id: s
        for s in db.query(RequirementSubmission).filter(
            RequirementSubmission.business_id == business_id
        ).all()
    }

    items = []
    for template in applicable_templates:
        if template.id in existing_submissions:
            sub = existing_submissions[template.id]
            items.append({
                "id": sub.id,
                "template_id": template.id,
                "label": template.label,
                "is_required": template.is_required,
                "hauler_type": template.hauler_type,
                "is_submitted": sub.is_submitted,
                "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
                "notes": sub.notes,
            })
        else:
            new_sub = RequirementSubmission(
                business_id=business_id,
                template_id=template.id,
                is_submitted=False,
            )
            db.add(new_sub)
            db.flush()
            items.append({
                "id": new_sub.id,
                "template_id": template.id,
                "label": template.label,
                "is_required": template.is_required,
                "hauler_type": template.hauler_type,
                "is_submitted": False,
                "submitted_at": None,
                "notes": None,
            })
    
    db.commit()

    submitted_count = sum(1 for i in items if i["is_submitted"])

    return {
        "business_id": business_id,
        "hauler_type": hauler_value,
        "total": len(items),
        "submitted": submitted_count,
        "pending": len(items) - submitted_count,
        "items": items,
    }


@router.patch("/business/{business_id}/submission/{submission_id}")
def toggle_submission(
    business_id:   int,
    submission_id: int,
    data:          SubmissionToggle,
    db:            Session = Depends(get_db),
    current_user:  User    = Depends(staff_only)
):
    submission = db.query(RequirementSubmission).filter(
        RequirementSubmission.id          == submission_id,
        RequirementSubmission.business_id == business_id,
    ).first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    submission.is_submitted = data.is_submitted
    submission.submitted_at = datetime.utcnow() if data.is_submitted else None
    submission.submitted_by = current_user.id   if data.is_submitted else None
    submission.notes        = data.notes
    submission.updated_at   = datetime.utcnow()
    db.commit()

    log_audit(
        db, current_user.id, "UPDATE_REQUIREMENT", "BUSINESS",
        business_id,
        {"submission_id": submission_id, "is_submitted": data.is_submitted},
    )

    return {"message": "Updated", "is_submitted": submission.is_submitted}
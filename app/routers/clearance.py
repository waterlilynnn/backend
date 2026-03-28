from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from typing import List, Optional
import os
from pathlib import Path

from app.core.database import get_db
from app.core.security import staff_only, admin_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.clearance import Clearance
from app.models.requirement import RequirementTemplate, RequirementSubmission
from app.utils.pdf_generator import generate_clearance_pdf

router = APIRouter(
    prefix="/clearance",
    tags=["Clearance"]
)


# helpers
def _format_owner(b: BusinessRecord) -> str:
    if b.owner_last_name and b.owner_first_name:
        name = f"{b.owner_last_name}, {b.owner_first_name}"
        if b.owner_middle_name:
            name += f" {b.owner_middle_name[0]}."
        if b.owner_suffix:
            name += f" {b.owner_suffix}"
        return name
    return b.owner_name_raw or "—"


def _check_requirements_complete(db: Session, business_id: int) -> tuple[bool, list[str]]:
    """Return (all_done, list_of_missing_required_labels)."""
    hauler_value = None
    business = db.query(BusinessRecord).filter(BusinessRecord.id == business_id).first()
    if business:
        hauler_value = (
            business.hauler_type.value
            if hasattr(business.hauler_type, 'value')
            else str(business.hauler_type)
        )

    # Get all active required templates applicable to this hauler
    required_templates = db.query(RequirementTemplate).filter(
        RequirementTemplate.is_active == True,
        RequirementTemplate.is_required == True,
    ).filter(
        (RequirementTemplate.hauler_type == None) |
        (RequirementTemplate.hauler_type == hauler_value)
    ).all()

    if not required_templates:
        return True, []

    # Check which ones are submitted
    submitted_ids = {
        s.template_id
        for s in db.query(RequirementSubmission).filter(
            RequirementSubmission.business_id == business_id,
            RequirementSubmission.is_submitted == True,
        ).all()
    }

    missing = [t.label for t in required_templates if t.id not in submitted_ids]
    return len(missing) == 0, missing


# pending clearances
@router.get("/pending")
def get_pending_clearances(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    businesses = db.query(BusinessRecord).outerjoin(
        Clearance, Clearance.business_record_id == BusinessRecord.id
    ).filter(
        BusinessRecord.status == "Approved",
        Clearance.id == None
    ).order_by(BusinessRecord.approved_at.desc()).all()

    color_map = {
        "Barangay": "Blue", "City": "Yellow", "Accredited": "Purple",
        "Hazardous": "Red", "Exempted": "Green", "No Contract": "Gray"
    }

    result = []
    for b in businesses:
        hauler_str = b.hauler_type.value if hasattr(b.hauler_type, 'value') else b.hauler_type
        result.append({
            "business_id": b.id,
            "business_name": b.establishment_name,
            "owner": _format_owner(b),
            "control_number": b.control_number,
            "hauler_type": hauler_str,
            "clearance_color": color_map.get(hauler_str, "White"),
            "approved_at": b.approved_at.isoformat() if b.approved_at else None,
        })

    return result


# generate clerance
@router.post("/generate/{business_id}")
def generate_clearance(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == business_id,
        BusinessRecord.status == "Approved"
    ).first()

    if not business:
        raise HTTPException(status_code=404, detail="Approved business not found")

    if business.has_violation:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate clearance: Business has unresolved violations"
        )

    if business.is_revoked:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate clearance: Business clearance is revoked"
        )

    # Requirements gate 
    all_done, missing = _check_requirements_complete(db, business_id)
    if not all_done:
        missing_str = ", ".join(missing[:5])
        suffix = f" (+{len(missing)-5} more)" if len(missing) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate clearance: Missing required documents — {missing_str}{suffix}"
        )

    # Return existing clearance if already generated
    existing = db.query(Clearance).filter(
        Clearance.business_record_id == business_id
    ).first()
    if existing:
        return {
            "message": "Clearance already exists",
            "clearance_id": existing.id,
            "control_number": existing.control_number,
        }

    # Generate control number if not already set
    if not business.control_number:
        year = datetime.now().year
        month = datetime.now().strftime("%m")
        latest = db.query(BusinessRecord).filter(
            BusinessRecord.control_number.like(f"EMC-{year}-{month}%")
        ).order_by(BusinessRecord.control_number.desc()).first()
        last_seq = int(latest.control_number[-4:]) if latest and latest.control_number else 0
        business.control_number = f"EMC-{year}-{month}-{last_seq + 1:04d}"
        business.date_issued = datetime.now().date()
        business.validity = datetime(year, 12, 31).date()
        db.commit()

    color_map = {
        "Barangay": "Blue", "City": "Yellow", "Accredited": "Purple",
        "Hazardous": "Red", "Exempted": "Green", "No Contract": "Gray"
    }
    hauler_str = business.hauler_type.value if hasattr(business.hauler_type, 'value') else business.hauler_type
    color = color_map.get(hauler_str, "White")

    clearance = Clearance(
        business_record_id=business_id,
        control_number=business.control_number,
        clearance_color=color,
        valid_until=datetime(datetime.now().year, 12, 31, 23, 59, 59),
        printed_by=current_user.id,
        printed_at=datetime.now(),
        is_active=True,
        is_claimed=False,
        print_count=0,
    )
    db.add(clearance)
    db.commit()
    db.refresh(clearance)

    log_audit(
        db, current_user.id, "GENERATE", "CLEARANCE",
        clearance.id, {"control_number": clearance.control_number}
    )

    return {
        "message": "Clearance generated successfully",
        "clearance_id": clearance.id,
        "control_number": clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until": clearance.valid_until,
    }


# issue clearance
@router.post("/issue/{clearance_id}")
def issue_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    clearance = db.query(Clearance).filter(Clearance.id == clearance_id).first()
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    clearance.is_claimed = True
    clearance.claimed_at = datetime.now()
    clearance.claimed_by = current_user.full_name
    db.commit()

    log_audit(
        db, current_user.id, "ISSUE", "CLEARANCE",
        clearance.id, {"control_number": clearance.control_number}
    )
    return {"message": "Clearance marked as issued", "clearance_id": clearance.id}


@router.get("/{clearance_id}")
def get_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    clearance = db.query(Clearance).filter(Clearance.id == clearance_id).first()
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == clearance.business_record_id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    return {
        "id": clearance.id,
        "business_record_id": business.id,
        "control_number": clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until": clearance.valid_until,
        "print_count": clearance.print_count,
        "printed_at": clearance.printed_at,
        "is_claimed": clearance.is_claimed,
        "business_name": business.establishment_name,
        "owner_name": _format_owner(business),
        "location": business.location,
        "hauler_type": business.hauler_type.value if hasattr(business.hauler_type, 'value') else business.hauler_type,
        "business_line": business.business_line,
        "bin_number": business.bin_number,
        "has_violation": business.has_violation,
    }


@router.post("/view/{clearance_id}")
def view_clearance_pdf(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    clearance = db.query(Clearance).filter(Clearance.id == clearance_id).first()
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == clearance.business_record_id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    clearance_data = {
        "control_number": clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until": clearance.valid_until.strftime("%B %d, %Y"),
        "establishment_name": business.establishment_name,
        "owner_name": _format_owner(business),
        "location": business.location,
        "hauler_type": business.hauler_type.value if hasattr(business.hauler_type, 'value') else business.hauler_type,
        "business_line": business.business_line,
        "bin_number": business.bin_number or "N/A",
        "issued_date": datetime.now().strftime("%m/%d/%Y"),
        "application_type": business.application_type.value if hasattr(business.application_type, 'value') else str(business.application_type),
        "issued_by": current_user.full_name,
    }

    filename = f"clearance_view_{clearance.control_number.replace('-', '_')}.pdf"
    pdf_path = generate_clearance_pdf(clearance_data, filename)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

    return FileResponse(
        path=pdf_path,
        filename=f"EMC_CLEARANCE_{clearance.control_number}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=EMC_CLEARANCE_{clearance.control_number}.pdf"}
    )


@router.post("/print/{clearance_id}")
def print_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    clearance = db.query(Clearance).filter(Clearance.id == clearance_id).first()
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == clearance.business_record_id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    clearance.print_count += 1
    clearance.last_printed_at = datetime.now()
    clearance.last_printed_by = current_user.id
    db.commit()

    clearance_data = {
        "control_number": clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until": clearance.valid_until.strftime("%B %d, %Y"),
        "establishment_name": business.establishment_name,
        "owner_name": _format_owner(business),
        "location": business.location,
        "hauler_type": business.hauler_type.value if hasattr(business.hauler_type, 'value') else business.hauler_type,
        "business_line": business.business_line,
        "bin_number": business.bin_number or "N/A",
        "issued_date": datetime.now().strftime("%m/%d/%Y"),
        "application_type": business.application_type.value if hasattr(business.application_type, 'value') else str(business.application_type),
        "issued_by": current_user.full_name,
    }

    filename = f"clearance_print_{clearance.control_number.replace('-', '_')}.pdf"
    pdf_path = generate_clearance_pdf(clearance_data, filename)

    log_audit(
        db, current_user.id, "PRINT", "CLEARANCE",
        clearance.id, {"control_number": clearance.control_number}
    )

    return FileResponse(
        path=pdf_path,
        filename=f"EMC_CLEARANCE_{clearance.control_number}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=EMC_CLEARANCE_{clearance.control_number}.pdf"}
    )


# clearance history 
@router.get("/history/all")
def get_clearance_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
    search: Optional[str] = None,
    limit: int = 100
):
    query = db.query(Clearance).options(
        joinedload(Clearance.business_record),
        joinedload(Clearance.printer_user),
        joinedload(Clearance.last_printer_user)
    )

    if search and len(search) >= 2:
        search_term = f"%{search}%"
        query = query.join(Clearance.business_record).filter(
            (BusinessRecord.establishment_name.ilike(search_term)) |
            (Clearance.control_number.ilike(search_term))
        )

    clearances = query.order_by(Clearance.created_at.desc()).limit(limit).all()

    result = []
    for c in clearances:
        b = c.business_record
        result.append({
            "id": c.id,
            "business_record_id": c.business_record_id,
            "control_number": c.control_number,
            "business_name": b.establishment_name if b else "Unknown",
            "owner_name": _format_owner(b) if b else "—",
            "clearance_color": c.clearance_color,
            "hauler_type": (b.hauler_type.value if hasattr(b.hauler_type, 'value') else str(b.hauler_type)) if b else None,
            "bin_number": b.bin_number if b else None,
            "printed_by": c.printer_user.full_name if c.printer_user else "Unknown",
            "last_printed_by": c.last_printer_user.full_name if c.last_printer_user else None,
            "printed_at": c.printed_at.isoformat() if c.printed_at else None,
            "last_printed_at": c.last_printed_at.isoformat() if c.last_printed_at else None,
            "print_count": c.print_count,
            "is_claimed": c.is_claimed,
            "has_violation": b.has_violation if b else False,
        })

    return result
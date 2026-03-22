from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func
from datetime import datetime
from typing import List, Optional
import os
from pathlib import Path

from app.core.database import get_db
from app.core.security import staff_only, admin_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.clearance import Clearance
from app.models.inspection import Inspection
from app.utils.pdf_generator import generate_clearance_pdf

router = APIRouter(
    prefix="/clearance",
    tags=["Clearance"]
)

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

    result = []
    for b in businesses:
        if b.owner_last_name and b.owner_first_name:
            owner_name = f"{b.owner_last_name}, {b.owner_first_name}"
            if b.owner_middle_name:
                owner_name += f" {b.owner_middle_name[0]}."
            if b.owner_suffix:
                owner_name += f" {b.owner_suffix}"
        else:
            owner_name = b.owner_name_raw or "—"

        color_map = {
            "Barangay": "Blue", "City": "Yellow", "Accredited": "Purple",
            "Hazardous": "Red", "Exempted": "Green", "No Contract": "Gray"
        }
        hauler_str = b.hauler_type.value if hasattr(b.hauler_type, 'value') else b.hauler_type
        color = color_map.get(hauler_str, "White")

        result.append({
            "business_id": b.id,
            "business_name": b.establishment_name,
            "owner": owner_name,
            "control_number": b.control_number,
            "hauler_type": hauler_str,
            "clearance_color": color,
            "approved_at": b.approved_at.isoformat() if b.approved_at else None
        })

    return result


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
        raise HTTPException(status_code=400, detail="Cannot generate clearance: Business has unresolved violations")

    if business.is_revoked:
        raise HTTPException(status_code=400, detail="Cannot generate clearance: Business clearance is revoked")

    existing = db.query(Clearance).filter(
        Clearance.business_record_id == business_id
    ).first()

    if existing:
        return {
            "message": "Clearance already exists",
            "clearance_id": existing.id,
            "control_number": existing.control_number
        }

    if not business.control_number:
        year = datetime.now().year
        month = datetime.now().strftime("%m")
        latest = db.query(BusinessRecord).filter(
            BusinessRecord.control_number.like(f"EMC-{year}-{month}%")
        ).order_by(BusinessRecord.control_number.desc()).first()
        if latest and latest.control_number:
            new_seq = int(latest.control_number[-4:]) + 1
        else:
            new_seq = 1
        business.control_number = f"EMC-{year}-{month}-{new_seq:04d}"
        business.date_issued = datetime.now().date()
        business.validity = datetime(year, 12, 31).date()
        db.commit()

    color_map = {
        "Barangay": "Blue", "City": "Yellow", "Accredited": "Purple",
        "Hazardous": "Red", "Exempted": "Green", "No Contract": "Gray"
    }
    hauler_str = business.hauler_type.value if hasattr(business.hauler_type, 'value') else business.hauler_type
    color = color_map.get(hauler_str, "White")
    year = datetime.now().year
    expires_at = datetime(year, 12, 31, 23, 59, 59)

    clearance = Clearance(
        business_record_id=business_id,
        control_number=business.control_number,
        clearance_color=color,
        valid_until=expires_at,
        printed_by=current_user.id,
        printed_at=datetime.now(),
        is_active=True,
        is_claimed=False,
        print_count=0,
        last_printed_at=None,
        last_printed_by=None
    )

    db.add(clearance)
    db.commit()
    db.refresh(clearance)

    log_audit(db, current_user.id, "GENERATE", "CLEARANCE", clearance.id, {"control_number": clearance.control_number})

    return {
        "message": "Clearance generated successfully",
        "clearance_id": clearance.id,
        "control_number": clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until": clearance.valid_until
    }


@router.post("/revoke/{clearance_id}")
def revoke_clearance(
    clearance_id: int,
    reason: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Revoke a clearance due to violation. Sets business.is_revoked = True."""
    clearance = db.query(Clearance).filter(Clearance.id == clearance_id).first()
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    business = db.query(BusinessRecord).filter(BusinessRecord.id == clearance.business_record_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    # Mark clearance inactive
    clearance.is_active = False
    # Mark business as revoked
    business.is_revoked = True
    business.revoked_date = datetime.now().date()
    business.revoked_reason = reason

    db.commit()

    log_audit(db, current_user.id, "REVOKE", "CLEARANCE", clearance.id, {
        "control_number": clearance.control_number,
        "reason": reason
    })

    return {"message": "Clearance revoked", "clearance_id": clearance_id}


@router.post("/reissue/{business_id}")
def reissue_clearance(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Re-issue clearance for a revoked business after violation is resolved."""
    business = db.query(BusinessRecord).filter(BusinessRecord.id == business_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    if business.has_violation:
        raise HTTPException(status_code=400, detail="Cannot re-issue: Business still has unresolved violation")

    if not business.is_revoked:
        raise HTTPException(status_code=400, detail="Business clearance is not revoked")

    # Clear revocation
    business.is_revoked = False
    business.reissued_date = datetime.now().date()

    # Deactivate old clearance
    old = db.query(Clearance).filter(
        Clearance.business_record_id == business_id
    ).first()
    if old:
        old.is_active = False

    # Create new clearance
    year = datetime.now().year
    expires_at = datetime(year, 12, 31, 23, 59, 59)
    color_map = {
        "Barangay": "Blue", "City": "Yellow", "Accredited": "Purple",
        "Hazardous": "Red", "Exempted": "Green", "No Contract": "Gray"
    }
    hauler_str = business.hauler_type.value if hasattr(business.hauler_type, 'value') else business.hauler_type
    color = color_map.get(hauler_str, "White")

    new_clearance = Clearance(
        business_record_id=business_id,
        control_number=business.control_number,
        clearance_color=color,
        valid_until=expires_at,
        printed_by=current_user.id,
        printed_at=datetime.now(),
        is_active=True,
        is_claimed=False,
        print_count=0,
    )
    db.add(new_clearance)
    db.commit()
    db.refresh(new_clearance)

    log_audit(db, current_user.id, "REISSUE", "CLEARANCE", new_clearance.id, {
        "control_number": new_clearance.control_number,
        "business_id": business_id
    })

    return {
        "message": "Clearance re-issued successfully",
        "clearance_id": new_clearance.id,
        "control_number": new_clearance.control_number
    }


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

    log_audit(db, current_user.id, "ISSUE", "CLEARANCE", clearance.id, {"control_number": clearance.control_number})

    return {"message": "Clearance marked as issued", "clearance_id": clearance.id}


@router.get("/stats/dashboard")
def get_clearance_dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Aggregate stats for admin dashboard."""
    total_businesses  = db.query(BusinessRecord).count()
    total_clearances  = db.query(Clearance).count()
    issued_clearances = db.query(Clearance).filter(Clearance.is_claimed == True).count()
    total_inspections = db.query(Inspection).count()
    with_violations   = db.query(BusinessRecord).filter(BusinessRecord.has_violation == True).count()

    # Revoked: businesses where is_revoked=True (currently revoked)
    revoked = db.query(BusinessRecord).filter(BusinessRecord.is_revoked == True).count()

    # Re-issued: businesses that have a reissued_date set (meaning they were revoked and got new clearance)
    reissued = db.query(BusinessRecord).filter(BusinessRecord.reissued_date != None).count()

    return {
        "total_businesses":  total_businesses,
        "total_clearances":  total_clearances,
        "issued_clearances": issued_clearances,
        "total_inspections": total_inspections,
        "with_violations":   with_violations,
        "revoked_clearances": revoked,
        "reissued_clearances": reissued,
    }


@router.get("/{clearance_id}")
def get_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    clearance = db.query(Clearance).filter(Clearance.id == clearance_id).first()
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    business = db.query(BusinessRecord).filter(BusinessRecord.id == clearance.business_record_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    if business.owner_last_name and business.owner_first_name:
        owner_name = f"{business.owner_last_name}, {business.owner_first_name}"
        if business.owner_middle_name:
            owner_name += f" {business.owner_middle_name[0]}."
        if business.owner_suffix:
            owner_name += f" {business.owner_suffix}"
    else:
        owner_name = business.owner_name_raw or "—"

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
        "owner_name": owner_name,
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

    business = db.query(BusinessRecord).filter(BusinessRecord.id == clearance.business_record_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    if business.owner_last_name and business.owner_first_name:
        owner_name = f"{business.owner_last_name}, {business.owner_first_name}"
        if business.owner_middle_name:
            owner_name += f" {business.owner_middle_name[0]}."
        if business.owner_suffix:
            owner_name += f" {business.owner_suffix}"
    else:
        owner_name = business.owner_name_raw or "—"

    clearance_data = {
        "control_number": clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until": clearance.valid_until.strftime("%B %d, %Y"),
        "establishment_name": business.establishment_name,
        "owner_name": owner_name,
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

    business = db.query(BusinessRecord).filter(BusinessRecord.id == clearance.business_record_id).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    clearance.print_count += 1
    clearance.last_printed_at = datetime.now()
    clearance.last_printed_by = current_user.id
    db.commit()

    if business.owner_last_name and business.owner_first_name:
        owner_name = f"{business.owner_last_name}, {business.owner_first_name}"
        if business.owner_middle_name:
            owner_name += f" {business.owner_middle_name[0]}."
        if business.owner_suffix:
            owner_name += f" {business.owner_suffix}"
    else:
        owner_name = business.owner_name_raw or "—"

    clearance_data = {
        "control_number": clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until": clearance.valid_until.strftime("%B %d, %Y"),
        "establishment_name": business.establishment_name,
        "owner_name": owner_name,
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

    log_audit(db, current_user.id, "PRINT", "CLEARANCE", clearance.id, {"control_number": clearance.control_number})

    return FileResponse(
        path=pdf_path,
        filename=f"EMC_CLEARANCE_{clearance.control_number}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename=EMC_CLEARANCE_{clearance.control_number}.pdf"}
    )


@router.get("/history/all")
def get_clearance_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
    search: Optional[str] = None,
    limit: int = 200
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
        business     = c.business_record
        first_printer = c.printer_user
        last_printer  = c.last_printer_user

        hauler_type = None
        if business:
            hauler_type = business.hauler_type.value if hasattr(business.hauler_type, 'value') else str(business.hauler_type)

        owner_name = "—"
        if business:
            if business.owner_last_name and business.owner_first_name:
                owner_name = f"{business.owner_last_name}, {business.owner_first_name}"
                if business.owner_middle_name:
                    owner_name += f" {business.owner_middle_name[0]}."
                if business.owner_suffix:
                    owner_name += f" {business.owner_suffix}"
            elif business.owner_name_raw:
                owner_name = business.owner_name_raw

        result.append({
            "id": c.id,
            "business_record_id": c.business_record_id,
            "control_number": c.control_number,
            "business_name": business.establishment_name if business else "Unknown",
            "owner_name": owner_name,
            "clearance_color": c.clearance_color,
            "hauler_type": hauler_type,
            "location": business.location if business else None,
            "printed_by": first_printer.full_name if first_printer else "Unknown",
            "last_printed_by": last_printer.full_name if last_printer else None,
            "printed_at": c.printed_at.isoformat() if c.printed_at else None,
            "last_printed_at": c.last_printed_at.isoformat() if c.last_printed_at else None,
            "print_count": c.print_count,
            "is_claimed": c.is_claimed,
            "is_active": c.is_active,
            "has_violation": business.has_violation if business else False,
            "bin_number": business.bin_number if business else None,
        })

    return result
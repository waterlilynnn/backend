from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from typing import List
import os
from pathlib import Path

from app.core.database import get_db
from app.core.security import staff_only, admin_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.clearance import Clearance
from app.utils.pdf_generator import generate_clearance_pdf

router = APIRouter(
    prefix="/clearance",
    tags=["Clearance"]
)

# Get pending clearances (businesses without clearance)
@router.get("/pending")
def get_pending_clearances(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Get approved businesses without clearance"""
    
    businesses = db.query(BusinessRecord).outerjoin(
        Clearance, Clearance.business_record_id == BusinessRecord.id
    ).filter(
        BusinessRecord.status == "Approved",
        Clearance.id == None
    ).order_by(BusinessRecord.approved_at.desc()).all()
    
    result = []
    for b in businesses:
        # Format owner name
        if b.owner_last_name and b.owner_first_name:
            owner_name = f"{b.owner_last_name}, {b.owner_first_name}"
            if b.owner_middle_name:
                owner_name += f" {b.owner_middle_name[0]}."
            if b.owner_suffix:
                owner_name += f" {b.owner_suffix}"
        else:
            owner_name = b.owner_name_raw or "—"
        
        # Get color based on hauler type
        color_map = {
            "Barangay": "Blue",
            "City": "Yellow", 
            "Accredited": "Purple",
            "Hazardous": "Red",
            "Exempted": "Green",
            "No Contract": "Gray"
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

# Generate clearance
@router.post("/generate/{business_id}")
def generate_clearance(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Generate clearance for approved business - checks for violations first"""
    
    # Check if business exists and is approved
    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == business_id,
        BusinessRecord.status == "Approved"
    ).first()
    
    if not business:
        raise HTTPException(
            status_code=404,
            detail="Approved business not found"
        )
    
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
    
    # Check if clearance already exists
    existing = db.query(Clearance).filter(
        Clearance.business_record_id == business_id
    ).first()
    
    if existing:
        return {
            "message": "Clearance already exists",
            "clearance_id": existing.id,
            "control_number": existing.control_number
        }
    
    # Get control number from business
    if not business.control_number:
        # Generate control number if business doesn't have one
        year = datetime.now().year
        month = datetime.now().strftime("%m")
        
        latest = db.query(BusinessRecord).filter(
            BusinessRecord.control_number.like(f"EMC-{year}-{month}%")
        ).order_by(BusinessRecord.control_number.desc()).first()
        
        if latest and latest.control_number:
            last_seq = int(latest.control_number[-4:])
            new_seq = last_seq + 1
        else:
            new_seq = 1
        
        business.control_number = f"EMC-{year}-{month}-{new_seq:04d}"
        business.date_issued = datetime.now().date()
        business.validity = datetime(year, 12, 31).date()
        db.commit()
    
    # Determine color based on hauler type
    color_map = {
        "Barangay": "Blue",
        "City": "Yellow",
        "Accredited": "Purple",
        "Hazardous": "Red",
        "Exempted": "Green",
        "No Contract": "Gray"
    }
    hauler_str = business.hauler_type.value if hasattr(business.hauler_type, 'value') else business.hauler_type
    color = color_map.get(hauler_str, "White")
    
    # Expiration (Dec 31 of current year)
    year = datetime.now().year
    expires_at = datetime(year, 12, 31, 23, 59, 59)
    
    # Create clearance with business control number
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
    
    # Log audit
    log_audit(
        db, current_user.id, "GENERATE", "CLEARANCE", 
        clearance.id, {"control_number": clearance.control_number}
    )
    
    return {
        "message": "Clearance generated successfully",
        "clearance_id": clearance.id,
        "control_number": clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until": clearance.valid_until
    }

# Issue clearance (mark as issued)
@router.post("/issue/{clearance_id}")
def issue_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Mark clearance as issued to business owner"""
    
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
    
    return {
        "message": "Clearance marked as issued",
        "clearance_id": clearance.id
    }

# Get clearance by ID (for view page)
@router.get("/{clearance_id}")
def get_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Get clearance details with business info"""
    
    clearance = db.query(Clearance).filter(
        Clearance.id == clearance_id
    ).first()
    
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")
    
    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == clearance.business_record_id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Format owner name
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
    }

# Get clearance PDF for VIEWING (does not increment print count)
@router.post("/view/{clearance_id}")
def view_clearance_pdf(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """View clearance PDF without incrementing print count"""
    
    clearance = db.query(Clearance).filter(
        Clearance.id == clearance_id
    ).first()
    
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")
    
    # Get business details
    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == clearance.business_record_id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Format owner name
    if business.owner_last_name and business.owner_first_name:
        owner_name = f"{business.owner_last_name}, {business.owner_first_name}"
        if business.owner_middle_name:
            owner_name += f" {business.owner_middle_name[0]}."
        if business.owner_suffix:
            owner_name += f" {business.owner_suffix}"
    else:
        owner_name = business.owner_name_raw or "—"
    
    # Prepare data for PDF
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
    
    # Generate PDF filename
    filename = f"clearance_view_{clearance.control_number.replace('-', '_')}.pdf"
    
    # Generate PDF
    from app.utils.pdf_generator import generate_clearance_pdf
    pdf_path = generate_clearance_pdf(clearance_data, filename)
    
    return FileResponse(
        path=pdf_path,
        filename=f"EMC_CLEARANCE_{clearance.control_number}.pdf",
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=EMC_CLEARANCE_{clearance.control_number}.pdf"
        }
    )

# Print clearance (increments print count)
@router.post("/print/{clearance_id}")
def print_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Print clearance - increments print count"""
    
    clearance = db.query(Clearance).filter(
        Clearance.id == clearance_id
    ).first()
    
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")
    
    # Get business details
    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == clearance.business_record_id
    ).first()
    
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")
    
    # Increment print count
    clearance.print_count += 1
    clearance.last_printed_at = datetime.now()
    clearance.last_printed_by = current_user.id
    
    db.commit()
    
    # Format owner name
    if business.owner_last_name and business.owner_first_name:
        owner_name = f"{business.owner_last_name}, {business.owner_first_name}"
        if business.owner_middle_name:
            owner_name += f" {business.owner_middle_name[0]}."
        if business.owner_suffix:
            owner_name += f" {business.owner_suffix}"
    else:
        owner_name = business.owner_name_raw or "—"
    
    # Prepare data for PDF
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
    
    # Generate PDF filename
    filename = f"clearance_print_{clearance.control_number.replace('-', '_')}.pdf"
    
    # Generate PDF
    from app.utils.pdf_generator import generate_clearance_pdf
    pdf_path = generate_clearance_pdf(clearance_data, filename)
    
    log_audit(
        db, current_user.id, "PRINT", "CLEARANCE", 
        clearance.id, {"control_number": clearance.control_number}
    )
    
    return FileResponse(
        path=pdf_path,
        filename=f"EMC_CLEARANCE_{clearance.control_number}.pdf",
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=EMC_CLEARANCE_{clearance.control_number}.pdf"
        }
    )

# Get clearance history
@router.get("/history/all")
def get_clearance_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
    limit: int = 100
):
    """Get all clearances with printer info"""
    
    clearances = db.query(Clearance).options(
        joinedload(Clearance.business_record),
        joinedload(Clearance.printer_user),
        joinedload(Clearance.last_printer_user)
    ).order_by(
        Clearance.created_at.desc()
    ).limit(limit).all()
    
    result = []
    for c in clearances:
        business = c.business_record
        first_printer = c.printer_user
        last_printer = c.last_printer_user
        
        # Get hauler type from business
        hauler_type = None
        if business:
            hauler_type = business.hauler_type.value if hasattr(business.hauler_type, 'value') else str(business.hauler_type)
        
        # Format owner name
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
            "printed_by": first_printer.full_name if first_printer else "Unknown",
            "last_printed_by": last_printer.full_name if last_printer else None,
            "printed_at": c.printed_at.isoformat() if c.printed_at else None,
            "last_printed_at": c.last_printed_at.isoformat() if c.last_printed_at else None,
            "print_count": c.print_count,
            "is_claimed": c.is_claimed,
            "has_violation": business.has_violation if business else False
        })
    
    return result
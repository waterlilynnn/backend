from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime
from sqlalchemy import desc

from app.core.database import get_db
from app.core.security import staff_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.inspection import Inspection, InspectionStatus

router = APIRouter(
    prefix="/inspections",
    tags=["Inspections"]
)

@router.post("/business/{record_id}")
def create_inspection(
    record_id: int,
    status: InspectionStatus = Query(..., description="PASSED or WITH VIOLATION"),
    remarks: Optional[str] = Query(None),
    scanned_from_qr: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Record an inspection for a business"""
    
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")
    
    inspection = Inspection(
        business_record_id=record_id,
        inspector_id=current_user.id,
        status=status,
        remarks=remarks,
        scanned_from_qr=scanned_from_qr,
        is_resolved=False
    )
    
    db.add(inspection)
    db.flush()
    
    if status == InspectionStatus.WITH_VIOLATION:
        record.has_violation = True
        record.violation_date = datetime.now().date()
        record.violation_details = remarks
        record.violation_status = "Pending"
    else:
        record.has_violation = False
        record.violation_date = None
        record.violation_details = None
        record.violation_status = "None"
    
    db.commit()
    
    log_audit(
        db, current_user.id, "INSPECT", "BUSINESS", 
        record_id, {
            "status": status.value,
            "inspection_id": inspection.id
        }
    )
    
    return {
        "message": "Inspection recorded successfully",
        "inspection_id": inspection.id,
        "status": status.value,
        "business_violation_status": record.has_violation
    }

@router.post("/{inspection_id}/resolve")
def resolve_inspection(
    inspection_id: int,
    resolved_remarks: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Mark a WITH VIOLATION inspection as resolved"""
    
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    
    if inspection.status != InspectionStatus.WITH_VIOLATION:
        raise HTTPException(status_code=400, detail="Only violations can be resolved")
    
    if inspection.is_resolved:
        raise HTTPException(status_code=400, detail="Violation already resolved")
    
    inspection.is_resolved = True
    inspection.resolved_at = datetime.utcnow()
    inspection.resolved_by = current_user.id
    inspection.resolved_remarks = resolved_remarks
    
    # Check if business still has other unresolved violations
    record = db.query(BusinessRecord).filter(
        BusinessRecord.id == inspection.business_record_id
    ).first()
    
    if record:
        # Check for remaining unresolved violations
        unresolved = db.query(Inspection).filter(
            Inspection.business_record_id == record.id,
            Inspection.status == InspectionStatus.WITH_VIOLATION,
            Inspection.is_resolved == False,
            Inspection.id != inspection_id
        ).count()
        
        if unresolved == 0:
            record.has_violation = False
            record.violation_status = "Resolved"
    
    db.commit()
    
    log_audit(
        db, current_user.id, "RESOLVE", "BUSINESS",
        inspection.business_record_id,
        {"inspection_id": inspection_id, "resolved_remarks": resolved_remarks}
    )
    
    return {
        "message": "Violation resolved successfully",
        "inspection_id": inspection_id,
        "resolved_at": inspection.resolved_at
    }

@router.get("/business/{record_id}")
def get_inspections(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Get inspection history for a business (latest first)"""
    inspections = db.query(Inspection).options(
        joinedload(Inspection.resolver)
    ).filter(
        Inspection.business_record_id == record_id
    ).order_by(desc(Inspection.inspection_date)).all()
    
    return [
        {
            "id": i.id,
            "date": i.inspection_date,
            "status": i.status.value,
            "remarks": i.remarks,
            "inspector": i.inspector.full_name if i.inspector else None,
            "scanned_from_qr": i.scanned_from_qr,
            "is_resolved": i.is_resolved,
            "resolved_at": i.resolved_at,
            "resolved_by": i.resolver.full_name if i.resolver else None,
            "resolved_remarks": i.resolved_remarks,
        }
        for i in inspections
    ]

@router.get("/all")
def get_all_inspections(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Get all inspections across all businesses"""
    inspections = db.query(Inspection).options(
        joinedload(Inspection.business_record),
        joinedload(Inspection.inspector),
        joinedload(Inspection.resolver)
    ).order_by(desc(Inspection.inspection_date)).all()
    
    result = []
    for i in inspections:
        biz = i.business_record
        result.append({
            "id": i.id,
            "business_record_id": i.business_record_id,
            "establishment_name": biz.establishment_name if biz else "—",
            "bin_number": biz.bin_number if biz else None,
            "hauler_type": biz.hauler_type.value if biz and biz.hauler_type else None,
            "location": biz.location if biz else None,
            "date": i.inspection_date,
            "status": i.status.value,
            "remarks": i.remarks,
            "inspector": i.inspector.full_name if i.inspector else None,
            "scanned_from_qr": i.scanned_from_qr,
            "is_resolved": i.is_resolved,
            "resolved_at": i.resolved_at,
            "resolved_by": i.resolver.full_name if i.resolver else None,
            "resolved_remarks": i.resolved_remarks,
        })
    
    return result
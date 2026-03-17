from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
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
    
    # Create inspection
    inspection = Inspection(
        business_record_id=record_id,
        inspector_id=current_user.id,
        status=status,
        remarks=remarks,
        scanned_from_qr=scanned_from_qr
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

@router.get("/business/{record_id}")
def get_inspections(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Get inspection history for a business (latest first)"""
    inspections = db.query(Inspection).filter(
        Inspection.business_record_id == record_id
    ).order_by(desc(Inspection.inspection_date)).all()  
    
    return [
        {
            "id": i.id,
            "date": i.inspection_date,
            "status": i.status.value,
            "remarks": i.remarks,
            "inspector": i.inspector.full_name if i.inspector else None,
            "scanned_from_qr": i.scanned_from_qr
        }
        for i in inspections
    ]
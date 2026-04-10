from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.core.security import admin_only, staff_only, log_audit
from app.models.user import User
from app.services.archive_service import (
    get_archivable_records,
    archive_records,
    restore_from_archive,
    get_archived_records,
    get_records_to_notify
)

router = APIRouter(
    prefix="/archive",
    tags=["Archive"]
)


@router.get("/eligible")
def get_eligible_for_archive(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    """Get list of records eligible for archiving"""
    records = get_archivable_records(db)
    
    result = []
    for record in records:
        result.append({
            "id": record.id,
            "establishment_name": record.establishment_name,
            "owner_name": f"{record.owner_last_name}, {record.owner_first_name}" if record.owner_last_name else record.owner_name_raw,
            "created_at": record.created_at.isoformat(),
            "status": record.status,
        })
    
    return {
        "total": len(result),
        "records": result
    }


@router.post("/run")
def run_archive(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    """Manually run archiving process"""
    count = archive_records(db, current_user.id)
    
    log_audit(
        db, current_user.id, "MANUAL_ARCHIVE", "SYSTEM",
        None, {"archived_count": count}
    )
    
    return {
        "message": f"Archived {count} record(s)",
        "archived_count": count
    }


@router.post("/restore/{record_id}")
def restore_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    """Restore an archived record back to active status"""
    success = restore_from_archive(db, record_id, current_user.id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Archived record not found")
    
    return {"message": "Record restored successfully"}


@router.get("/list")
def list_archived_records(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Get list of archived records"""
    return get_archived_records(db, page, per_page)


@router.get("/pending-notification")
def get_pending_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    """Get records that will be archived soon (for admin notification)"""
    records = get_records_to_notify(db)
    return {"records": records, "count": len(records)}
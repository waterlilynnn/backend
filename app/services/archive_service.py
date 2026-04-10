from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json

from app.models.business_record import BusinessRecord
from app.models.setting import SystemSetting
from app.models.audit_log import AuditLog
from app.utils.email import send_email


def _load_archive_settings(db: Session) -> dict:
    """Load archive settings from database"""
    setting = db.query(SystemSetting).filter(SystemSetting.key == "archive_settings").first()
    if not setting or not setting.value:
        return {
            "auto_archive_enabled": False,
            "archive_after_years": 3,
            "archive_status": "ARCHIVED",
            "notify_before_days": 30,
        }
    try:
        return json.loads(setting.value)
    except:
        return {
            "auto_archive_enabled": False,
            "archive_after_years": 3,
            "archive_status": "ARCHIVED",
            "notify_before_days": 30,
        }


def get_archivable_records(db: Session) -> List[BusinessRecord]:
    """Get records that are eligible for archiving"""
    settings = _load_archive_settings(db)
    if not settings.get("auto_archive_enabled", False):
        return []
    
    years = settings.get("archive_after_years", 3)
    cutoff_date = datetime.utcnow().replace(year=datetime.utcnow().year - years)
    archive_status = settings.get("archive_status", "ARCHIVED")
    
    records = db.query(BusinessRecord).filter(
        BusinessRecord.created_at <= cutoff_date,
        BusinessRecord.status != archive_status
    ).all()
    
    return records


def get_records_to_notify(db: Session) -> List[Dict[str, Any]]:
    """Get records that will be archived soon"""
    settings = _load_archive_settings(db)
    if not settings.get("auto_archive_enabled", False):
        return []
    
    years = settings.get("archive_after_years", 3)
    days_before = settings.get("notify_before_days", 30)
    
    cutoff_date = datetime.utcnow().replace(year=datetime.utcnow().year - years)
    notify_date = cutoff_date - timedelta(days=days_before)
    
    records = db.query(BusinessRecord).filter(
        BusinessRecord.created_at <= notify_date,
        BusinessRecord.status != "ARCHIVED"
    ).all()
    
    result = []
    for record in records:
        result.append({
            "business_id": record.id,
            "business_name": record.establishment_name,
            "owner_name": f"{record.owner_last_name}, {record.owner_first_name}" if record.owner_last_name else record.owner_name_raw,
            "created_at": record.created_at,
            "will_be_archived_on": cutoff_date,
        })
    
    return result


def archive_records(db: Session, user_id: int = None) -> int:
    """Archive eligible records and return count"""
    settings = _load_archive_settings(db)
    years = settings.get("archive_after_years", 3)
    archive_status = settings.get("archive_status", "ARCHIVED")
    
    cutoff_date = datetime.utcnow().replace(year=datetime.utcnow().year - years)
    
    records = db.query(BusinessRecord).filter(
        BusinessRecord.created_at <= cutoff_date,
        BusinessRecord.status != archive_status
    ).all()
    
    count = 0
    for record in records:
        old_status = record.status
        record.status = archive_status
        record.updated_at = datetime.utcnow()
        count += 1
        
        # Log each archived record
        if user_id:
            log = AuditLog(
                user_id=user_id,
                action="ARCHIVE",
                entity_type="BUSINESS",
                entity_id=record.id,
                details={
                    "old_status": old_status,
                    "new_status": archive_status,
                    "cutoff_date": cutoff_date.isoformat()
                }
            )
            db.add(log)
    
    db.commit()
    return count


def restore_from_archive(db: Session, record_id: int, user_id: int = None) -> bool:
    record = db.query(BusinessRecord).filter(
        BusinessRecord.id == record_id,
        BusinessRecord.status == "ARCHIVED"
    ).first()
    
    if not record:
        return False
    
    old_status = record.status
    record.status = "Approved"
    record.updated_at = datetime.utcnow()
    
    if user_id:
        log = AuditLog(
            user_id=user_id,
            action="RESTORE",
            entity_type="BUSINESS",
            entity_id=record.id,
            details={
                "old_status": old_status,
                "new_status": "Approved"
            }
        )
        db.add(log)
    
    db.commit()
    return True


def get_archived_records(db: Session, page: int = 1, per_page: int = 20):
    """Get paginated list of archived records"""
    offset = (page - 1) * per_page
    
    total = db.query(BusinessRecord).filter(BusinessRecord.status == "ARCHIVED").count()
    
    records = db.query(BusinessRecord).filter(
        BusinessRecord.status == "ARCHIVED"
    ).order_by(BusinessRecord.updated_at.desc()).offset(offset).limit(per_page).all()
    
    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "items": records
    }
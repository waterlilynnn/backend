from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import List, Dict, Any
import json

from app.models.business_record import BusinessRecord
from app.models.setting import SystemSetting
from app.models.audit_log import AuditLog


def _load_archive_settings(db: Session) -> dict:
    setting = db.query(SystemSetting).filter(SystemSetting.key == "archive_settings").first()
    default = {
        "auto_archive_enabled": False,
        "archive_after_years":  1,
        "notify_before_days":   30,
    }
    if not setting or not setting.value:
        return default
    try:
        return {**default, **json.loads(setting.value)}
    except Exception:
        return default


def _subtract_years(dt: datetime, years: int) -> datetime:
    """Safely subtract years from a datetime (handles leap years)."""
    try:
        return dt.replace(year=dt.year - years)
    except ValueError:
        # Feb 29 in a year that isn't a leap year → use Feb 28
        return dt.replace(year=dt.year - years, day=28)


def get_archivable_records(db: Session) -> List[BusinessRecord]:
    settings = _load_archive_settings(db)
    if not settings.get("auto_archive_enabled", False):
        return []

    years       = int(settings.get("archive_after_years", 1))
    cutoff_date = _subtract_years(datetime.utcnow(), years)

    return (
        db.query(BusinessRecord)
        .filter(
            BusinessRecord.created_at <= cutoff_date,
            BusinessRecord.status != "ARCHIVED",
        )
        .all()
    )


def get_records_to_notify(db: Session) -> List[Dict[str, Any]]:
    settings = _load_archive_settings(db)
    if not settings.get("auto_archive_enabled", False):
        return []

    years        = int(settings.get("archive_after_years", 1))
    days_before  = int(settings.get("notify_before_days", 30))
    cutoff_date  = _subtract_years(datetime.utcnow(), years)
    notify_after = cutoff_date - timedelta(days=days_before)

    records = (
        db.query(BusinessRecord)
        .filter(
            BusinessRecord.created_at <= notify_after,
            BusinessRecord.status != "ARCHIVED",
        )
        .all()
    )

    result = []
    for record in records:
        owner = (
            f"{record.owner_last_name}, {record.owner_first_name}"
            if record.owner_last_name
            else record.owner_name_raw or "—"
        )
        result.append({
            "business_id":         record.id,
            "business_name":       record.establishment_name,
            "owner_name":          owner,
            "created_at":          record.created_at.isoformat() if record.created_at else None,
            "will_be_archived_on": cutoff_date.isoformat(),
        })
    return result


def archive_records(db: Session, user_id: int = None) -> int:
    settings    = _load_archive_settings(db)
    years       = int(settings.get("archive_after_years", 1))
    cutoff_date = _subtract_years(datetime.utcnow(), years)

    records = (
        db.query(BusinessRecord)
        .filter(
            BusinessRecord.created_at <= cutoff_date,
            BusinessRecord.status != "ARCHIVED",
        )
        .all()
    )

    count = 0
    for record in records:
        old_status    = record.status
        record.status = "ARCHIVED"
        record.updated_at = datetime.utcnow()
        count += 1

        if user_id:
            db.add(AuditLog(
                user_id     = user_id,
                action      = "ARCHIVE",
                entity_type = "BUSINESS",
                entity_id   = record.id,
                details     = {
                    "old_status":   old_status,
                    "new_status":   "ARCHIVED",
                    "cutoff_date":  cutoff_date.isoformat(),
                },
            ))

    db.commit()
    return count


def restore_from_archive(db: Session, record_id: int, user_id: int = None) -> bool:
    record = (
        db.query(BusinessRecord)
        .filter(
            BusinessRecord.id     == record_id,
            BusinessRecord.status == "ARCHIVED",
        )
        .first()
    )
    if not record:
        return False

    record.status     = "Approved"
    record.updated_at = datetime.utcnow()

    if user_id:
        db.add(AuditLog(
            user_id     = user_id,
            action      = "RESTORE",
            entity_type = "BUSINESS",
            entity_id   = record.id,
            details     = {"old_status": "ARCHIVED", "new_status": "Approved"},
        ))

    db.commit()
    return True


def get_archived_records(db: Session, page: int = 1, per_page: int = 20) -> dict:
    offset = (page - 1) * per_page
    total  = db.query(BusinessRecord).filter(BusinessRecord.status == "ARCHIVED").count()
    records = (
        db.query(BusinessRecord)
        .filter(BusinessRecord.status == "ARCHIVED")
        .order_by(BusinessRecord.updated_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = []
    for r in records:
        items.append({
            "id":               r.id,
            "establishment_name": r.establishment_name,
            "bin_number":       r.bin_number,
            "owner_last_name":  r.owner_last_name,
            "owner_first_name": r.owner_first_name,
            "owner_name_raw":   r.owner_name_raw,
            "status":           r.status,
            "created_at":       r.created_at.isoformat() if r.created_at else None,
            "updated_at":       r.updated_at.isoformat() if r.updated_at else None,
        })

    return {
        "total":       total,
        "page":        page,
        "per_page":    per_page,
        "total_pages": (total + per_page - 1) // per_page,
        "items":       items,
    }
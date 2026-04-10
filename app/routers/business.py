from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date

from app.core.database import get_db
from app.core.security import staff_only, admin_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord, HaulerType
from app.models.setting import SystemSetting
from app.schemas.business import (
    BusinessCreate, BusinessUpdate, BusinessResponse,
    BusinessSearchResponse,
)

router = APIRouter(
    prefix="/business-records",
    tags=["Business Records"]
)

ARCHIVED_STATUS = "ARCHIVED"


def generate_control_number(db: Session, application_type: str, existing_business=None) -> str:
    year = datetime.now().year
    month = datetime.now().strftime("%m")

    if application_type == "RENEWAL" and existing_business and existing_business.control_number:
        return existing_business.control_number

    prefix = f"EMC-{year}-{month}-"
    latest = (
        db.query(BusinessRecord)
        .filter(BusinessRecord.control_number.like(f"{prefix}%"))
        .order_by(BusinessRecord.control_number.desc())
        .first()
    )

    last_seq = 0
    if latest and latest.control_number:
        try:
            seq_part = latest.control_number.split("-")[-1]
            last_seq = int(seq_part)
        except (ValueError, IndexError):
            last_seq = 0

    return f"{prefix}{last_seq + 1:04d}"


def check_duplicate_business(db: Session, establishment_name: str, location: str, exclude_id: int = None):
    query = db.query(BusinessRecord).filter(
        BusinessRecord.establishment_name.ilike(establishment_name),
        BusinessRecord.location == location,
        BusinessRecord.status != ARCHIVED_STATUS,
    )
    if exclude_id:
        query = query.filter(BusinessRecord.id != exclude_id)
    return query.first()


@router.post("/", response_model=BusinessResponse, status_code=status.HTTP_201_CREATED)
def create_business_record(
    data: BusinessCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    duplicate = check_duplicate_business(db, data.establishment_name, data.location)
    if duplicate:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Business '{data.establishment_name}' already exists in {data.location}",
        )

    if data.bin_number and data.bin_number.strip():
        from app.utils.bin_validator import validate_bin_number
        setting = db.query(SystemSetting).filter(SystemSetting.key == "bin_formats").first()
        formats_json = setting.value if setting else None
        is_valid, error_msg = validate_bin_number(data.bin_number, formats_json)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg or "Invalid BIN number format",
            )

    existing = None
    if data.bin_number and data.bin_number.strip():
        existing = db.query(BusinessRecord).filter(
            BusinessRecord.bin_number == data.bin_number.strip(),
            BusinessRecord.status != ARCHIVED_STATUS,
        ).first()

    control_number = generate_control_number(db, data.application_type, existing)
    previous_record_id = existing.id if existing and data.application_type == "RENEWAL" else None

    business = BusinessRecord(
        bin_number=data.bin_number,
        establishment_name=data.establishment_name,
        business_line=data.business_line,
        owner_last_name=data.owner_last_name.upper() if data.owner_last_name else None,
        owner_first_name=data.owner_first_name.upper() if data.owner_first_name else None,
        owner_middle_name=data.owner_middle_name.upper() if data.owner_middle_name else None,
        owner_suffix=data.owner_suffix,
        contact_number=data.contact_number,
        email=data.email,
        location=data.location,
        has_own_structure=data.has_own_structure,
        hauler_type=data.hauler_type,
        application_type=data.application_type,
        created_by=current_user.id,
        status="Approved",
        control_number=control_number,
        date_issued=datetime.now().date(),
        validity=datetime(datetime.now().year, 12, 31).date(),
        previous_record_id=previous_record_id,
    )

    db.add(business)
    db.commit()
    db.refresh(business)

    log_audit(
        db, current_user.id, "CREATE", "BUSINESS",
        business.id, {
            "name": business.establishment_name,
            "control_number": business.control_number,
            "type": business.application_type.value if hasattr(business.application_type, "value") else str(business.application_type),
            "location": business.location,
        },
    )

    return business


@router.get("/search", response_model=List[BusinessSearchResponse])
def search_business_records(
    q: str = Query("", min_length=2, description="Search query"),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    if not q or len(q) < 2:
        return []

    search_term = f"%{q}%"
    base_query = (
        db.query(BusinessRecord)
        .filter(
            BusinessRecord.status != ARCHIVED_STATUS,
            (
                (BusinessRecord.establishment_name.ilike(search_term)) |
                (BusinessRecord.owner_last_name.ilike(search_term)) |
                (BusinessRecord.owner_first_name.ilike(search_term)) |
                (BusinessRecord.owner_name_raw.ilike(search_term)) |
                (BusinessRecord.bin_number.ilike(search_term))
            )
        )
        .order_by(BusinessRecord.created_at.desc())
    )

    total = base_query.count()
    results = base_query.offset((page - 1) * per_page).limit(per_page).all()

    response_data = []
    for record in results:
        if record.owner_last_name and record.owner_first_name:
            owner_name = f"{record.owner_last_name}, {record.owner_first_name}"
            if record.owner_middle_name:
                owner_name += f" {record.owner_middle_name[0]}."
            if record.owner_suffix:
                owner_name += f" {record.owner_suffix}"
        else:
            owner_name = record.owner_name_raw or "—"

        app_type = "NEW"
        if record.application_type:
            app_type = record.application_type.value if hasattr(record.application_type, "value") else str(record.application_type)

        app_date = record.application_date or record.created_at

        response_data.append({
            "id": record.id,
            "establishment_name": record.establishment_name,
            "owner_name": owner_name,
            "bin_number": record.bin_number,
            "location": record.location,
            "hauler_type": record.hauler_type.value if hasattr(record.hauler_type, "value") else str(record.hauler_type),
            "status": record.status,
            "control_number": record.control_number,
            "has_violation": record.has_violation,
            "violation_details": record.violation_details,
            "business_line": record.business_line,
            "application_type": app_type,
            "application_date": app_date.isoformat() if app_date else None,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "_total": total,
            "_page": page,
            "_per_page": per_page,
            "_total_pages": (total + per_page - 1) // per_page,
        })

    return response_data


@router.get("/recent", response_model=dict)
def get_recent_business_records(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    offset = (page - 1) * per_page
    base = db.query(BusinessRecord).filter(BusinessRecord.status != ARCHIVED_STATUS)
    total_count = base.count()

    results = (
        base
        .order_by(BusinessRecord.created_at.desc())
        .offset(offset)
        .limit(per_page)
        .all()
    )

    items = []
    for record in results:
        if record.owner_last_name and record.owner_first_name:
            owner_name = f"{record.owner_last_name}, {record.owner_first_name}"
            if record.owner_middle_name:
                owner_name += f" {record.owner_middle_name[0]}."
            if record.owner_suffix:
                owner_name += f" {record.owner_suffix}"
        else:
            owner_name = record.owner_name_raw or "—"

        app_type = "NEW"
        if record.application_type:
            app_type = record.application_type.value if hasattr(record.application_type, "value") else str(record.application_type)

        app_date = record.application_date or record.created_at

        items.append({
            "id": record.id,
            "establishment_name": record.establishment_name,
            "owner_name": owner_name,
            "bin_number": record.bin_number,
            "location": record.location,
            "hauler_type": record.hauler_type.value if hasattr(record.hauler_type, "value") else str(record.hauler_type),
            "status": record.status,
            "control_number": record.control_number,
            "has_violation": record.has_violation,
            "violation_details": record.violation_details,
            "business_line": record.business_line,
            "application_type": app_type,
            "application_date": app_date,
            "created_at": record.created_at,
        })

    return {
        "items": items,
        "total": total_count,
        "page": page,
        "per_page": per_page,
        "total_pages": (total_count + per_page - 1) // per_page,
    }


@router.get("/all")
def get_all_business_records(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    try:
        results = (
            db.query(BusinessRecord)
            .filter(BusinessRecord.status != ARCHIVED_STATUS)
            .order_by(BusinessRecord.created_at.desc())
            .all()
        )
        response_data = []
        for record in results:
            if record.owner_last_name and record.owner_first_name:
                owner_name = f"{record.owner_last_name}, {record.owner_first_name}"
                if record.owner_middle_name:
                    owner_name += f" {record.owner_middle_name[0]}."
                if record.owner_suffix:
                    owner_name += f" {record.owner_suffix}"
            else:
                owner_name = record.owner_name_raw or "—"

            response_data.append({
                "id": record.id,
                "establishment_name": record.establishment_name or "",
                "owner_name": owner_name,
                "bin_number": record.bin_number,
                "location": record.location,
                "hauler_type": record.hauler_type.value if record.hauler_type else "",
                "status": record.status or "Pending",
                "control_number": record.control_number,
                "has_violation": bool(record.has_violation),
                "violation_details": record.violation_details,
                "business_line": record.business_line or "",
                "application_type": record.application_type.value if record.application_type else "NEW",
                "application_date": record.application_date.isoformat() if record.application_date else None,
                "created_at": record.created_at.isoformat() if record.created_at else None,
            })
        return response_data
    except Exception as e:
        import traceback
        traceback.print_exc()
        return []


@router.get("/{record_id}", response_model=BusinessResponse)
def get_business_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")
    return record


@router.put("/{record_id}", response_model=BusinessResponse)
def update_business_record(
    record_id: int,
    data: BusinessUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")

    if record.status == ARCHIVED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Archived records cannot be edited. Please restore first.",
        )

    if data.establishment_name and data.location:
        duplicate = check_duplicate_business(db, data.establishment_name, data.location, record_id)
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Business '{data.establishment_name}' already exists in {data.location}",
            )

    if data.bin_number and data.bin_number.strip() and data.bin_number != record.bin_number:
        from app.utils.bin_validator import validate_bin_number
        setting = db.query(SystemSetting).filter(SystemSetting.key == "bin_formats").first()
        formats_json = setting.value if setting else None
        is_valid, error_msg = validate_bin_number(data.bin_number, formats_json)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=error_msg or "Invalid BIN number format",
            )

    changes = {}
    update_data = data.dict(exclude_unset=True)

    for key, value in update_data.items():
        if value is not None:
            old_value = getattr(record, key)
            if old_value != value:
                changes[key] = {"old": str(old_value), "new": str(value)}
                setattr(record, key, value)

    for name_field in ("owner_last_name", "owner_first_name", "owner_middle_name"):
        if name_field in update_data and update_data[name_field]:
            setattr(record, name_field, update_data[name_field].upper())

    record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(record)

    log_audit(
        db, current_user.id, "UPDATE", "BUSINESS",
        record.id, {"name": record.establishment_name, "changes": changes},
    )

    return record


@router.delete("/{record_id}")
def delete_business_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")

    log_audit(
        db, current_user.id, "DELETE", "BUSINESS",
        record.id, {"name": record.establishment_name},
    )

    db.delete(record)
    db.commit()

    return {"message": "Business record deleted successfully"}
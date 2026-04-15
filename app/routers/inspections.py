from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional
from datetime import datetime, timedelta
import json

from app.core.database import get_db
from app.core.security import staff_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.setting import SystemSetting
from app.models.inspection import Inspection, InspectionStatus
from app.models.inspection_checklist import InspectionChecklist
from app.schemas.inspection import InspectionChecklistCreate

router = APIRouter(prefix="/inspections", tags=["Inspections"])

ARCHIVED_STATUS = "ARCHIVED"

VIOLATION_LABELS = {
    "littering_public":             "Littering in Public Areas",
    "open_burning":                 "Open Burning of Waste",
    "mixing_recyclables":           "Mixing Recyclables with Solid Wastes",
    "prohibited_packaging":         "Use of Prohibited Packaging Materials",
    "single_use_plastics":          "Use of Single-Use Plastics for Food/Drinks",
    "polluting_water":              "Polluting Water Bodies",
    "discharging_without_permit":   "Discharging Without Permits",
    "refusal_of_inspection":        "Refusal of Inspections",
    "hazardous_without_compliance": "Use of Hazardous Substances Without Compliance",
}


def _is_business_line_exempted_from_inspection(db: Session, business_line: str) -> bool:
    setting = db.query(SystemSetting).filter(SystemSetting.key == "exempted_inspection_lines").first()
    if not setting or not setting.value:
        return False
    try:
        exempted_lines = json.loads(setting.value)
        return business_line in exempted_lines
    except:
        return False


def _derive_status(payload: dict) -> InspectionStatus:
    violations = payload.get("violations") or {}
    return (
        InspectionStatus.WITH_VIOLATION
        if any(bool(v) for v in violations.values())
        else InspectionStatus.PASSED
    )


def _active_violation_labels(violations: dict) -> list[str]:
    if not violations:
        return []
    return [VIOLATION_LABELS.get(k, k) for k, v in violations.items() if v]


@router.get("/business/{record_id}/can-inspect")
def can_inspect_business(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Check if business can be inspected (one inspection per calendar year)"""
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")
    
    if _is_business_line_exempted_from_inspection(db, record.business_line):
        return {"can_inspect": False, "reason": "exempted"}
    
    current_year = datetime.utcnow().year
    
    # Check if there's an inspection in the current year
    inspection_this_year = db.query(Inspection).filter(
        Inspection.business_record_id == record_id,
        Inspection.inspection_date >= datetime(current_year, 1, 1)
    ).first()
    
    if inspection_this_year:
        # If there's a violation, check if within 15 days to allow resolution
        if inspection_this_year.status == InspectionStatus.WITH_VIOLATION and not inspection_this_year.is_resolved:
            days_since = (datetime.utcnow() - inspection_this_year.inspection_date).days
            if days_since <= 15:
                return {
                    "can_inspect": True, 
                    "reason": "violation_resolution",
                    "inspection_id": inspection_this_year.id,
                    "days_remaining": 15 - days_since
                }
        
        return {
            "can_inspect": False, 
            "reason": "already_inspected",
            "inspection_date": inspection_this_year.inspection_date.isoformat()
        }
    
    return {"can_inspect": True, "reason": None}


@router.post("/business/{record_id}/checklist")
def submit_inspection_checklist(
    record_id: int,
    data: InspectionChecklistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")
    
    if _is_business_line_exempted_from_inspection(db, record.business_line):
        raise HTTPException(
            status_code=400,
            detail=f"This business line '{record.business_line}' is exempted from inspections. No inspection required."
        )
    
    current_year = datetime.utcnow().year
    
    # Check if already inspected this year (with violation resolution window)
    existing_inspection = db.query(Inspection).filter(
        Inspection.business_record_id == record_id,
        Inspection.inspection_date >= datetime(current_year, 1, 1)
    ).first()
    
    if existing_inspection:
        if existing_inspection.status == InspectionStatus.WITH_VIOLATION and not existing_inspection.is_resolved:
            days_since = (datetime.utcnow() - existing_inspection.inspection_date).days
            if days_since > 15:
                raise HTTPException(
                    status_code=400,
                    detail=f"Violation from inspection on {existing_inspection.inspection_date.strftime('%B %d, %Y')} is over 15 days old. Please contact administrator."
                )
        else:
            raise HTTPException(
                status_code=400,
                detail=f"This business has already been inspected in {current_year}. Only one inspection per calendar year is allowed."
            )

    payload = data.dict()
    status = _derive_status(payload)
    active_violations = _active_violation_labels(payload.get("violations") or {})
    violation_details = "; ".join(active_violations) if active_violations else None

    summary_text = payload.get("summary_other") if payload.get("summary") == "Other" else payload.get("summary")

    inspection = Inspection(
        business_record_id=record_id,
        inspector_id=current_user.id,
        status=status,
        remarks=summary_text,
        scanned_from_qr=False,
    )
    db.add(inspection)
    db.flush()

    checklist = InspectionChecklist(
        inspection_id        = inspection.id,
        emb_ecc              = payload.get("emb_ecc"),
        emb_cnc              = payload.get("emb_cnc"),
        pamb_clearance       = payload.get("pamb_clearance"),
        discharge_permit     = payload.get("discharge_permit"),
        sanitary_permit      = payload.get("sanitary_permit"),
        business_permit      = payload.get("business_permit"),
        swm_facilities       = payload.get("swm_facilities"),
        sw_hauling           = payload.get("sw_hauling"),
        has_iec_materials    = payload.get("has_iec_materials"),
        proper_segregation   = payload.get("proper_segregation"),
        wwt_facilities       = payload.get("wwt_facilities"),
        desludging           = payload.get("desludging"),
        desludging_other     = payload.get("desludging_other"),
        violations           = payload.get("violations"),
        summary              = payload.get("summary"),
        summary_other        = payload.get("summary_other"),
        recommendations      = payload.get("recommendations"),
        recommendations_other= payload.get("recommendations_other"),
    )
    db.add(checklist)

    if status == InspectionStatus.WITH_VIOLATION:
        record.has_violation    = True
        record.violation_date   = datetime.now().date()
        record.violation_details = violation_details
        record.violation_status = "Pending"
    else:
        record.has_violation    = False
        record.violation_date   = None
        record.violation_details = None
        record.violation_status = "None"

    db.commit()

    log_audit(
        db, current_user.id, "INSPECT", "BUSINESS",
        record_id, {
            "status": status.value,
            "inspection_id": inspection.id,
            "violations": active_violations,
        }
    )

    return {
        "message": "Inspection submitted successfully",
        "inspection_id": inspection.id,
        "status": status.value,
        "active_violations": active_violations,
        "business_violation_status": record.has_violation,
    }


@router.post("/resolve/{inspection_id}")
def resolve_inspection(
    inspection_id: int,
    resolved_remarks: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    inspection = db.query(Inspection).filter(Inspection.id == inspection_id).first()
    if not inspection:
        raise HTTPException(status_code=404, detail="Inspection not found")
    if inspection.status != InspectionStatus.WITH_VIOLATION:
        raise HTTPException(status_code=400, detail="No violation to resolve")
    
    # Check if within 15 days
    days_since = (datetime.utcnow() - inspection.inspection_date).days
    if days_since > 15:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resolve violation. The 15-day resolution period has passed (inspection was {days_since} days ago)."
        )

    inspection.is_resolved      = True
    inspection.resolved_at      = datetime.now()
    inspection.resolved_by      = current_user.id
    inspection.resolved_remarks = resolved_remarks

    record = db.query(BusinessRecord).filter(
        BusinessRecord.id == inspection.business_record_id
    ).first()
    if record:
        remaining = db.query(Inspection).filter(
            Inspection.business_record_id == record.id,
            Inspection.id != inspection_id,
            Inspection.status == InspectionStatus.WITH_VIOLATION,
            Inspection.is_resolved == False,
        ).count()
        if remaining == 0:
            record.has_violation    = False
            record.violation_status = "Resolved"

    db.commit()

    log_audit(db, current_user.id, "RESOLVE", "BUSINESS",
              inspection.business_record_id,
              {"inspection_id": inspection_id, "resolved_remarks": resolved_remarks})

    return {"message": "Violation resolved", "inspection_id": inspection_id}


@router.post("/business/{record_id}")
def create_inspection(
    record_id: int,
    status: InspectionStatus = Query(...),
    remarks: Optional[str] = Query(None),
    scanned_from_qr: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")
    
    if _is_business_line_exempted_from_inspection(db, record.business_line):
        raise HTTPException(
            status_code=400,
            detail=f"This business line '{record.business_line}' is exempted from inspections. No inspection required."
        )

    inspection = Inspection(
        business_record_id=record_id,
        inspector_id=current_user.id,
        status=status,
        remarks=remarks,
        scanned_from_qr=scanned_from_qr,
    )
    db.add(inspection)
    db.flush()

    if status == InspectionStatus.WITH_VIOLATION:
        record.has_violation    = True
        record.violation_date   = datetime.now().date()
        record.violation_details = remarks
        record.violation_status = "Pending"
    else:
        record.has_violation    = False
        record.violation_date   = None
        record.violation_details = None
        record.violation_status = "None"

    db.commit()
    log_audit(db, current_user.id, "INSPECT", "BUSINESS",
              record_id, {"status": status.value, "inspection_id": inspection.id})

    return {
        "message": "Inspection recorded",
        "inspection_id": inspection.id,
        "status": status.value,
        "business_violation_status": record.has_violation,
    }


@router.get("/business/{record_id}")
def get_inspections(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    inspections = db.query(Inspection).filter(
        Inspection.business_record_id == record_id
    ).order_by(desc(Inspection.inspection_date)).all()

    result = []
    for i in inspections:
        try:
            cl = i.checklist
        except Exception:
            cl = None

        result.append({
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
            "has_checklist": cl is not None,
            "checklist_id": cl.id if cl else None,
        })

    return result


@router.get("/checklist/{inspection_id}")
def get_inspection_checklist(
    inspection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    cl = db.query(InspectionChecklist).filter(
        InspectionChecklist.inspection_id == inspection_id
    ).first()
    if not cl:
        raise HTTPException(status_code=404, detail="Checklist not found")
    return cl


@router.get("/all")
def get_all_inspections(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    inspections = (
        db.query(Inspection)
        .join(BusinessRecord, Inspection.business_record_id == BusinessRecord.id)
        .filter(BusinessRecord.status != ARCHIVED_STATUS)
        .order_by(desc(Inspection.inspection_date))
        .all()
    )
    
    result = []
    for i in inspections:
        b = i.business_record
        result.append({
            "id": i.id,
            "business_record_id": i.business_record_id,
            "establishment_name": b.establishment_name if b else "—",
            "bin_number": b.bin_number if b else None,
            "business_line": b.business_line if b else None,
            "hauler_type": (b.hauler_type.value if hasattr(b.hauler_type, 'value') else str(b.hauler_type)) if b else None,
            "date": i.inspection_date.isoformat() if i.inspection_date else None,
            "status": i.status.value,
            "inspector": i.inspector.full_name if i.inspector else None,
            "remarks": i.remarks,
            "is_resolved": i.is_resolved,
            "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
            "resolved_by": i.resolver.full_name if i.resolver else None,
            "resolved_remarks": i.resolved_remarks,
        })
    return result


@router.get("/business/{record_id}/exempted-status")
def check_inspection_exempted(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")
    
    is_exempted = _is_business_line_exempted_from_inspection(db, record.business_line)
    
    return {
        "business_id": record_id,
        "business_line": record.business_line,
        "is_exempted_from_inspection": is_exempted
    }
    

@router.get("/business/{record_id}/can-inspect")
def can_inspect_business(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    from app.models.setting import SystemSetting
    import json
    from datetime import datetime
    
    record = db.query(BusinessRecord).filter(BusinessRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Business record not found")
    
    if _is_business_line_exempted_from_inspection(db, record.business_line):
        return {"can_inspect": False, "reason": "exempted"}
    
    setting = db.query(SystemSetting).filter(SystemSetting.key == "inspection_frequency").first()
    freq_config = {"frequency": 1, "period": "year"}
    if setting and setting.value:
        try:
            freq_config = json.loads(setting.value)
        except:
            pass
    
    frequency = freq_config.get("frequency", 1)
    period = freq_config.get("period", "year")
    
    last_inspection = db.query(Inspection).filter(
        Inspection.business_record_id == record_id
    ).order_by(Inspection.inspection_date.desc()).first()
    
    if not last_inspection:
        return {"can_inspect": True, "reason": None, "inspection_count": 0, "max_count": frequency, "period": period}
    
    now = datetime.utcnow()
    last_date = last_inspection.inspection_date
    
    if period == "year":
        if last_date.year == now.year:
            count_this_year = db.query(Inspection).filter(
                Inspection.business_record_id == record_id,
                Inspection.inspection_date >= datetime(now.year, 1, 1)
            ).count()
            return {
                "can_inspect": count_this_year < frequency,
                "reason": None if count_this_year < frequency else f"Maximum {frequency} inspection(s) per year reached",
                "inspection_count": count_this_year,
                "max_count": frequency,
                "period": period,
                "last_inspection_date": last_date.isoformat()
            }
        else:
            return {"can_inspect": True, "reason": None, "inspection_count": 0, "max_count": frequency, "period": period, "last_inspection_date": last_date.isoformat()}
    
    elif period == "half_year":
        from dateutil.relativedelta import relativedelta
        if last_date + relativedelta(months=6) <= now:
            return {"can_inspect": True, "reason": None, "inspection_count": 0, "max_count": frequency, "period": period, "last_inspection_date": last_date.isoformat()}
        else:
            return {"can_inspect": False, "reason": f"Maximum {frequency} inspection(s) per {period} reached", "inspection_count": 1, "max_count": frequency, "period": period, "last_inspection_date": last_date.isoformat()}
    
    elif period == "quarter":
        from dateutil.relativedelta import relativedelta
        if last_date + relativedelta(months=3) <= now:
            return {"can_inspect": True, "reason": None, "inspection_count": 0, "max_count": frequency, "period": period, "last_inspection_date": last_date.isoformat()}
        else:
            return {"can_inspect": False, "reason": f"Maximum {frequency} inspection(s) per {period} reached", "inspection_count": 1, "max_count": frequency, "period": period, "last_inspection_date": last_date.isoformat()}
    
    else:
        from dateutil.relativedelta import relativedelta
        if last_date + relativedelta(months=1) <= now:
            return {"can_inspect": True, "reason": None, "inspection_count": 0, "max_count": frequency, "period": period, "last_inspection_date": last_date.isoformat()}
        else:
            return {"can_inspect": False, "reason": f"Maximum {frequency} inspection(s) per {period} reached", "inspection_count": 1, "max_count": frequency, "period": period, "last_inspection_date": last_date.isoformat()}
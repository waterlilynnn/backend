from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from typing import List, Optional
import os
import json
from pathlib import Path

from app.core.database import get_db
from app.core.security import staff_only, admin_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.clearance import Clearance
from app.models.inspection import Inspection, InspectionStatus
from app.models.requirement import RequirementTemplate, RequirementSubmission
from app.models.setting import SystemSetting
from app.utils.pdf_generator import generate_clearance_pdf, get_sticker_year
from app.utils.email import send_email

router = APIRouter(prefix="/clearance", tags=["Clearance"])

ARCHIVED_STATUS = "ARCHIVED"


def _format_owner(b: BusinessRecord) -> str:
    if b.owner_last_name and b.owner_first_name:
        name = f"{b.owner_last_name}, {b.owner_first_name}"
        if b.owner_middle_name:
            name += f" {b.owner_middle_name[0]}."
        if b.owner_suffix:
            name += f" {b.owner_suffix}"
        return name
    return b.owner_name_raw or "—"


def _get_signatories(db: Session) -> dict:
    defaults = {
        "recommending_name":      "ANTONETTE NICOLE D. BAYOT",
        "recommending_title":     "ENGINEER I",
        "recommending_signature": None,
        "approving_name":         "OSCAR B. LAURENCIANA",
        "approving_title":        "OIC-CENRO",
        "approving_signature":    None,
    }
    setting = db.query(SystemSetting).filter(SystemSetting.key == "signatories").first()
    if setting and setting.value:
        try:
            data = json.loads(setting.value)
            return {**defaults, **data}
        except Exception:
            pass
    return defaults


def _is_business_line_exempted(db: Session, business_line: str) -> bool:
    if not business_line:
        return False
    setting = db.query(SystemSetting).filter(
        SystemSetting.key == "exempted_business_lines"
    ).first()
    if not setting or not setting.value:
        return False
    try:
        exempted = json.loads(setting.value)
        return business_line in exempted
    except Exception:
        return False


def _is_business_line_exempted_from_inspection(db: Session, business_line: str) -> bool:
    if not business_line:
        return False
    setting = db.query(SystemSetting).filter(
        SystemSetting.key == "exempted_inspection_lines"
    ).first()
    if not setting or not setting.value:
        return False
    try:
        exempted = json.loads(setting.value)
        return business_line in exempted
    except Exception:
        return False


def _check_requirements_complete(db: Session, business_id: int) -> tuple[bool, list[str]]:
    business = db.query(BusinessRecord).filter(BusinessRecord.id == business_id).first()
    if not business:
        return True, []

    if _is_business_line_exempted(db, business.business_line):
        return True, []

    hauler_value = (
        business.hauler_type.value
        if hasattr(business.hauler_type, "value")
        else str(business.hauler_type)
    )

    required_templates = (
        db.query(RequirementTemplate)
        .filter(
            RequirementTemplate.is_active == True,
            RequirementTemplate.is_required == True,
        )
        .filter(
            (RequirementTemplate.hauler_type.is_(None)) |
            (RequirementTemplate.hauler_type == hauler_value)
        )
        .all()
    )

    if not required_templates:
        return True, []

    submitted_ids = {
        s.template_id
        for s in db.query(RequirementSubmission)
        .filter(
            RequirementSubmission.business_id == business_id,
            RequirementSubmission.is_submitted == True,
        )
        .all()
    }

    missing = [t.label for t in required_templates if t.id not in submitted_ids]
    return len(missing) == 0, missing


def _check_has_passed_inspection(db: Session, business_id: int) -> tuple[bool, str]:
    business = db.query(BusinessRecord).filter(BusinessRecord.id == business_id).first()
    if not business:
        return False, "Business not found"

    if _is_business_line_exempted_from_inspection(db, business.business_line):
        return True, ""

    inspections = (
        db.query(Inspection)
        .filter(Inspection.business_record_id == business_id)
        .order_by(Inspection.inspection_date.desc())
        .all()
    )

    if not inspections:
        return False, "Business has not been inspected yet. Please conduct an inspection first."

    has_unresolved_violation = any(
        i.status == InspectionStatus.WITH_VIOLATION and not i.is_resolved
        for i in inspections
    )
    if has_unresolved_violation:
        return False, "Business has unresolved violation(s). Please resolve all violations before generating clearance."

    has_passed = any(i.status == InspectionStatus.PASSED for i in inspections)
    if not has_passed:
        return False, "No passed inspection found. Please conduct a passing inspection before generating clearance."

    return True, ""


def _build_clearance_data(business: BusinessRecord, clearance: Clearance, issued_by: str, db: Session) -> dict:
    sigs = _get_signatories(db)
    return {
        "control_number":    clearance.control_number,
        "clearance_color":   clearance.clearance_color,
        "valid_until":       clearance.valid_until.strftime("%B %d, %Y"),
        "establishment_name": business.establishment_name,
        "owner_name":        _format_owner(business),
        "location":          business.location,
        "hauler_type": (
            business.hauler_type.value
            if hasattr(business.hauler_type, "value")
            else business.hauler_type
        ),
        "business_line":     business.business_line,
        "bin_number":        business.bin_number or "N/A",
        "issued_date":       datetime.now().strftime("%m/%d/%Y"),
        "application_type": (
            business.application_type.value
            if hasattr(business.application_type, "value")
            else str(business.application_type)
        ),
        "issued_by":               issued_by,
        "recommending_name":       sigs.get("recommending_name",  ""),
        "recommending_title":      sigs.get("recommending_title", ""),
        "recommending_signature":  sigs.get("recommending_signature"),
        "approving_name":          sigs.get("approving_name",     ""),
        "approving_title":         sigs.get("approving_title",    ""),
        "approving_signature":     sigs.get("approving_signature"),
    }


@router.get("/pending")
def get_pending_clearances(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    businesses = (
        db.query(BusinessRecord)
        .outerjoin(Clearance, Clearance.business_record_id == BusinessRecord.id)
        .filter(
            BusinessRecord.status == "Approved",
            Clearance.id.is_(None),
        )
        .order_by(BusinessRecord.approved_at.desc())
        .all()
    )

    color_map = {
        "Barangay": "Blue", "City": "Yellow", "Accredited": "Purple",
        "Hazardous": "Red", "Exempted": "Green", "No Contract": "Gray",
    }

    result = []
    for b in businesses:
        hauler_str = b.hauler_type.value if hasattr(b.hauler_type, "value") else b.hauler_type
        result.append({
            "business_id":    b.id,
            "business_name":  b.establishment_name,
            "owner":          _format_owner(b),
            "control_number": b.control_number,
            "hauler_type":    hauler_str,
            "clearance_color": color_map.get(hauler_str, "White"),
            "approved_at":    b.approved_at.isoformat() if b.approved_at else None,
        })
    return result


@router.post("/generate/{business_id}")
def generate_clearance(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == business_id,
        BusinessRecord.status == "Approved",
    ).first()

    if not business:
        raise HTTPException(status_code=404, detail="Approved business not found")

    if business.has_violation:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate clearance: Business has unresolved violations",
        )

    if business.is_revoked:
        raise HTTPException(
            status_code=400,
            detail="Cannot generate clearance: Business clearance is revoked",
        )

    insp_ok, insp_msg = _check_has_passed_inspection(db, business_id)
    if not insp_ok:
        raise HTTPException(status_code=400, detail=insp_msg)

    all_done, missing = _check_requirements_complete(db, business_id)
    if not all_done:
        missing_str = ", ".join(missing[:5])
        suffix = f" (+{len(missing) - 5} more)" if len(missing) > 5 else ""
        raise HTTPException(
            status_code=400,
            detail=f"Cannot generate clearance: Missing required documents — {missing_str}{suffix}",
        )

    existing_active = (
        db.query(Clearance)
        .filter(
            Clearance.business_record_id == business_id,
            Clearance.is_archived == False,
        )
        .first()
    )
    if existing_active:
        return {
            "message":        "Clearance already exists",
            "clearance_id":   existing_active.id,
            "control_number": existing_active.control_number,
        }

    if not business.control_number:
        year  = datetime.now().year
        month = datetime.now().strftime("%m")
        latest = (
            db.query(BusinessRecord)
            .filter(BusinessRecord.control_number.like(f"EMC-{year}-{month}-%"))
            .order_by(BusinessRecord.control_number.desc())
            .first()
        )
        last_seq = 0
        if latest and latest.control_number:
            try:
                last_seq = int(latest.control_number.split("-")[-1])
            except (ValueError, IndexError):
                last_seq = 0
        business.control_number = f"EMC-{year}-{month}-{last_seq + 1:04d}"
        business.date_issued    = datetime.now().date()
        business.validity       = datetime(year, 12, 31).date()
        db.commit()

    color_map = {
        "Barangay": "Blue", "City": "Yellow", "Accredited": "Purple",
        "Hazardous": "Red", "Exempted": "Green", "No Contract": "Gray",
    }
    hauler_str = (
        business.hauler_type.value if hasattr(business.hauler_type, "value") else business.hauler_type
    )
    color = color_map.get(hauler_str, "White")

    sticker_year = get_sticker_year()

    clearance = Clearance(
        business_record_id=business_id,
        control_number=business.control_number,
        clearance_color=color,
        valid_until=datetime(sticker_year, 12, 31, 23, 59, 59),
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
        clearance.id, {"control_number": clearance.control_number},
    )

    if business.email:
        send_email(
            to_email=business.email,
            subject="EMC System — Your Environmental Clearance Is Ready for Pickup",
            body=f"""
            <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
              <h2 style="color:#1a4a2e;">EMC System — Clearance Ready for Pickup</h2>
              <p>Dear <strong>{_format_owner(business)}</strong>,</p>
              <p>Your Environmental Management Clearance for
                 <strong>{business.establishment_name}</strong> has been
                 <strong>approved and is now ready for pickup</strong>.</p>
              <table style="border-collapse:collapse;width:100%;margin:16px 0;
                            background:#f0fdf4;border:1px solid #dcfce7;">
                <tr>
                  <td style="padding:12px;font-weight:bold;color:#166534;">Control Number</td>
                  <td style="padding:12px;font-family:monospace;">{clearance.control_number}</td>
                </tr>
                <tr style="background:#f8fafc;">
                  <td style="padding:12px;font-weight:bold;color:#166534;">Establishment</td>
                  <td style="padding:12px;">{business.establishment_name}</td>
                </tr>
              </table>
              <p style="color:#166534;font-size:13px;">
                Please proceed to the CENRO office to claim your clearance.
                Bring a valid ID upon claiming.
              </p>
              <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
              <p style="color:#999;font-size:12px;">
                City Environment and Natural Resources Office · Tagaytay City
              </p>
            </div>
            """,
        )

    return {
        "message":         "Clearance generated successfully",
        "clearance_id":    clearance.id,
        "control_number":  clearance.control_number,
        "clearance_color": clearance.clearance_color,
        "valid_until":     clearance.valid_until,
    }


@router.post("/issue/{clearance_id}")
def issue_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
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
        clearance.id, {"control_number": clearance.control_number},
    )

    biz = clearance.business_record
    if biz and biz.email:
        send_email(
            to_email=biz.email,
            subject="EMC System — Your Environmental Clearance Has Been Issued",
            body=f"""
            <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
              <h2 style="color:#1a4a2e;">EMC System — Clearance Officially Issued</h2>
              <p>Dear <strong>{_format_owner(biz)}</strong>,</p>
              <p>Your Environmental Management Clearance for
                 <strong>{biz.establishment_name}</strong> has been
                 <strong>officially issued</strong> on
                 {clearance.claimed_at.strftime("%B %d, %Y")}.</p>
              <table style="border-collapse:collapse;width:100%;margin:16px 0;
                            background:#f0fdf4;border:1px solid #dcfce7;">
                <tr>
                  <td style="padding:12px;font-weight:bold;color:#166534;">Control Number</td>
                  <td style="padding:12px;font-family:monospace;">{clearance.control_number}</td>
                </tr>
                <tr style="background:#f8fafc;">
                  <td style="padding:12px;font-weight:bold;color:#166534;">Issued By</td>
                  <td style="padding:12px;">{clearance.claimed_by}</td>
                </tr>
              </table>
              <p style="color:#166534;font-size:13px;">
                Please keep your clearance in a safe place. This is an official government document.
              </p>
              <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
              <p style="color:#999;font-size:12px;">
                City Environment and Natural Resources Office · Tagaytay City
              </p>
            </div>
            """,
        )

    return {"message": "Clearance marked as issued", "clearance_id": clearance.id}


@router.get("/{clearance_id}")
def get_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
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
        "id":                 clearance.id,
        "business_record_id": business.id,
        "control_number":     clearance.control_number,
        "clearance_color":    clearance.clearance_color,
        "valid_until":        clearance.valid_until,
        "print_count":        clearance.print_count,
        "printed_at":         clearance.printed_at,
        "is_claimed":         clearance.is_claimed,
        "is_archived":        clearance.is_archived,
        "business_name":      business.establishment_name,
        "owner_name":         _format_owner(business),
        "location":           business.location,
        "hauler_type": (
            business.hauler_type.value
            if hasattr(business.hauler_type, "value")
            else business.hauler_type
        ),
        "business_line":  business.business_line,
        "bin_number":     business.bin_number,
        "has_violation":  business.has_violation,
    }


@router.post("/view/{clearance_id}")
def view_clearance_pdf(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    clearance = db.query(Clearance).filter(Clearance.id == clearance_id).first()
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == clearance.business_record_id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    clearance_data = _build_clearance_data(business, clearance, current_user.full_name, db)

    filename = f"clearance_view_{clearance.control_number.replace('-', '_')}.pdf"
    pdf_path = generate_clearance_pdf(clearance_data, filename)

    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=500, detail="Failed to generate PDF")

    return FileResponse(
        path=pdf_path,
        filename=f"{clearance.control_number}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={clearance.control_number}.pdf"},
    )


@router.post("/print/{clearance_id}")
def print_clearance(
    clearance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    clearance = db.query(Clearance).filter(Clearance.id == clearance_id).first()
    if not clearance:
        raise HTTPException(status_code=404, detail="Clearance not found")

    business = db.query(BusinessRecord).filter(
        BusinessRecord.id == clearance.business_record_id
    ).first()
    if not business:
        raise HTTPException(status_code=404, detail="Business not found")

    clearance.print_count     += 1
    clearance.last_printed_at  = datetime.now()
    clearance.last_printed_by  = current_user.id
    db.commit()

    clearance_data = _build_clearance_data(business, clearance, current_user.full_name, db)

    filename = f"clearance_print_{clearance.control_number.replace('-', '_')}.pdf"
    pdf_path = generate_clearance_pdf(clearance_data, filename)

    log_audit(
        db, current_user.id, "PRINT", "CLEARANCE",
        clearance.id, {"control_number": clearance.control_number},
    )

    return FileResponse(
        path=pdf_path,
        filename=f"{clearance.control_number}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f"inline; filename={clearance.control_number}.pdf"},
    )


@router.get("/business/{business_id}/history")
def get_business_clearance_history(
    business_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    clearances = (
        db.query(Clearance)
        .options(
            joinedload(Clearance.printer_user),
            joinedload(Clearance.last_printer_user),
        )
        .filter(Clearance.business_record_id == business_id)
        .order_by(Clearance.created_at.desc())
        .all()
    )

    return [
        {
            "id":             c.id,
            "control_number": c.control_number,
            "clearance_color": c.clearance_color,
            "valid_until":    c.valid_until.isoformat() if c.valid_until else None,
            "printed_at":     c.printed_at.isoformat() if c.printed_at else None,
            "last_printed_at": c.last_printed_at.isoformat() if c.last_printed_at else None,
            "print_count":    c.print_count,
            "is_claimed":     c.is_claimed,
            "is_archived":    c.is_archived,
            "archived_at":    c.archived_at.isoformat() if c.archived_at else None,
            "printed_by":     c.printer_user.full_name if c.printer_user else "Unknown",
        }
        for c in clearances
    ]


@router.get("/history/all")
def get_clearance_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
    search: Optional[str] = None,
    limit: int = 100,
):
    query = db.query(Clearance).options(
        joinedload(Clearance.business_record),
        joinedload(Clearance.printer_user),
        joinedload(Clearance.last_printer_user),
    )

    if search and len(search) >= 2:
        search_term = f"%{search}%"
        query = query.join(Clearance.business_record).filter(
            BusinessRecord.status != ARCHIVED_STATUS,
            (
                (BusinessRecord.establishment_name.ilike(search_term)) |
                (Clearance.control_number.ilike(search_term))
            )
        )
    else:
        query = query.join(Clearance.business_record).filter(
            BusinessRecord.status != ARCHIVED_STATUS
        )

    clearances = query.order_by(Clearance.created_at.desc()).limit(limit).all()

    result = []
    for c in clearances:
        b = c.business_record
        result.append({
            "id":                 c.id,
            "business_record_id": c.business_record_id,
            "control_number":     c.control_number,
            "business_name":      b.establishment_name if b else "Unknown",
            "owner_name":         _format_owner(b) if b else "—",
            "clearance_color":    c.clearance_color,
            "hauler_type": (
                (b.hauler_type.value if hasattr(b.hauler_type, "value") else str(b.hauler_type))
                if b else None
            ),
            "bin_number":       b.bin_number if b else None,
            "printed_by":       c.printer_user.full_name if c.printer_user else "Unknown",
            "last_printed_by":  c.last_printer_user.full_name if c.last_printer_user else None,
            "printed_at":       c.printed_at.isoformat() if c.printed_at else None,
            "last_printed_at":  c.last_printed_at.isoformat() if c.last_printed_at else None,
            "print_count":      c.print_count,
            "is_claimed":       c.is_claimed,
            "is_archived":      c.is_archived,
            "archived_at":      c.archived_at.isoformat() if c.archived_at else None,
            "has_violation":    b.has_violation if b else False,
        })

    return result
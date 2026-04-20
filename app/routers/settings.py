from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import json, base64, secrets, string
from datetime import datetime
from pathlib import Path

from app.core.database import get_db
from app.core.security import admin_only, get_password_hash, log_audit
from app.models.user import User
from app.models.role import Role
from app.models.setting import SystemSetting
from app.models.requirement import RequirementTemplate, RequirementSubmission
from app.models.business_record import BusinessRecord
from app.models.clearance import Clearance
from app.schemas.setting import (
    SettingResponse, SettingUpdate,
    BinFormatsPayload, BinFormat,
    RequirementTemplateCreate, RequirementTemplateUpdate, RequirementTemplateResponse,
)
from app.utils.email import send_email

router = APIRouter(prefix="/admin/settings", tags=["Admin Settings"])

SIGNATURE_DIR = Path("uploads/signatures")
SIGNATURE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_BIN_FORMATS = [
    {"id": "fmt_1", "segments": [7, 4, 7],    "label": "7-4-7  (e.g. 0402119-2011-0000466)",    "is_active": True},
    {"id": "fmt_2", "segments": [3, 2, 4, 7], "label": "3-2-4-7 (e.g. 129-00-2025-0000197)", "is_active": True},
]


def _get_or_create_setting(db, key, default_value, label, category):
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not s:
        s = SystemSetting(key=key, value=default_value, label=label, category=category)
        db.add(s)
        db.commit()
        db.refresh(s)
    return s


def _load_setting(db, key, default):
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not s or not s.value:
        return default
    try:
        return json.loads(s.value)
    except:
        return default


def _save_setting(db, key, label, category, value, updated_by):
    s = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not s:
        s = SystemSetting(key=key, label=label, category=category)
        db.add(s)
    s.value = json.dumps(value)
    s.updated_by = updated_by
    s.updated_at = datetime.utcnow()
    db.commit()


def _gen_password(length=12):
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(chars) for _ in range(length))


# ============================================================================
# ARCHIVE SETTINGS (CLEARANCES ONLY)
# ============================================================================

_DEFAULT_ARCHIVE = {
    "auto_archive_enabled": False,
    "archive_after_years": 1,  # Archive clearances after 1 year
    "notify_before_days": 30,
}

# Sticker year cutoff: if month >= 11 (November), use next year
STICKER_CUTOFF_MONTH = 11


def get_sticker_year() -> int:
    """Determine sticker year based on cutoff (November)."""
    now = datetime.now()
    if now.month >= STICKER_CUTOFF_MONTH:
        return now.year + 1
    return now.year


@router.get("/archive")
def get_archive_settings(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    return _load_setting(db, "archive_settings", _DEFAULT_ARCHIVE)


@router.put("/archive")
def update_archive_settings(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    current = _load_setting(db, "archive_settings", _DEFAULT_ARCHIVE)
    current.update({k: v for k, v in payload.items() if k in _DEFAULT_ARCHIVE})
    _save_setting(db, "archive_settings", "Archive Settings", "general", current, current_user.id)
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "archive_settings"})
    return {"message": "Archive settings updated", **current}


@router.get("/archive/years")
def get_clearance_archive_years(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    """
    Get all years with clearances for archiving.
    Only counts clearances, not business records.
    """
    from sqlalchemy import func, extract
    
    # Get years from clearances table
    clearances_by_year = db.query(
        extract('year', Clearance.printed_at).label('year'),
        func.count(Clearance.id).label('count')
    ).group_by('year').order_by('year').all()
    
    result = []
    for c in clearances_by_year:
        year = int(c.year)
        # Check if clearances from this year are already archived
        year_clearances = db.query(Clearance).filter(
            extract('year', Clearance.printed_at) == year
        ).all()
        already_archived = all(clr.is_archived == True for clr in year_clearances) if year_clearances else False
        
        result.append({
            "year": year,
            "clearance_count": c.count,
            "already_archived": already_archived
        })
    
    # Sort by year descending
    result.sort(key=lambda x: x['year'], reverse=True)
    return result


@router.post("/archive/{year}")
def archive_clearances_by_year(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """
    Archive all clearances from a specific year.
    Business records remain ACTIVE - only clearances are archived.
    """
    from sqlalchemy import extract
    
    # Only archive clearances from the specified year that are not already archived
    clearances = db.query(Clearance).filter(
        extract('year', Clearance.printed_at) == year,
        Clearance.is_archived == False
    ).all()
    
    count = 0
    for clr in clearances:
        clr.is_archived = True
        clr.archived_at = datetime.utcnow()
        clr.archived_by = current_user.id
        count += 1
    
    db.commit()
    
    log_audit(
        db, current_user.id, "ARCHIVE_CLEARANCES", "CLEARANCE", None,
        {"year": year, "clearance_count": count}
    )
    
    return {
        "message": f"Archived {count} clearance(s) from {year}",
        "archived_count": count,
        "year": year
    }


@router.post("/unarchive/{year}")
def unarchive_clearances_by_year(
    year: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """
    Restore all archived clearances from a specific year.
    """
    from sqlalchemy import extract
    
    clearances = db.query(Clearance).filter(
        extract('year', Clearance.printed_at) == year,
        Clearance.is_archived == True
    ).all()
    
    count = 0
    for clr in clearances:
        clr.is_archived = False
        clr.unarchived_at = datetime.utcnow()
        clr.unarchived_by = current_user.id
        count += 1
    
    db.commit()
    
    log_audit(
        db, current_user.id, "UNARCHIVE_CLEARANCES", "CLEARANCE", None,
        {"year": year, "clearance_count": count}
    )
    
    return {
        "message": f"Restored {count} clearance(s) from {year}",
        "restored_count": count,
        "year": year
    }


@router.get("/sticker-year")
def get_current_sticker_year(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    """Get the current sticker year based on cutoff logic."""
    return {"sticker_year": get_sticker_year(), "cutoff_month": STICKER_CUTOFF_MONTH}


# ============================================================================
# BIN FORMATS
# ============================================================================

@router.get("/bin-formats/public")
def get_bin_formats_public(db: Session = Depends(get_db)):
    setting = _get_or_create_setting(db, "bin_formats", json.dumps(DEFAULT_BIN_FORMATS), "BIN Number Formats", "validation")
    return [f for f in json.loads(setting.value) if f.get("is_active", True)]


@router.get("/bin-formats", response_model=List[BinFormat])
def get_bin_formats(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    setting = _get_or_create_setting(db, "bin_formats", json.dumps(DEFAULT_BIN_FORMATS), "BIN Number Formats", "validation")
    return [BinFormat(**f) for f in json.loads(setting.value)]


@router.put("/bin-formats", response_model=List[BinFormat])
def update_bin_formats(payload: BinFormatsPayload, db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    if not payload.formats:
        raise HTTPException(400, "At least one BIN format is required")
    _save_setting(db, "bin_formats", "BIN Number Formats", "validation", [f.model_dump() for f in payload.formats], current_user.id)
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "bin_formats"})
    return payload.formats


# ============================================================================
# REQUIREMENTS
# ============================================================================

@router.get("/requirements", response_model=List[RequirementTemplateResponse])
def list_requirement_templates(
    include_inactive: bool = False,
    hauler_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    q = db.query(RequirementTemplate)
    if not include_inactive:
        q = q.filter(RequirementTemplate.is_active == True)
    if hauler_type:
        q = q.filter(
            (RequirementTemplate.hauler_type.is_(None)) |
            (RequirementTemplate.hauler_type == hauler_type)
        )
    return q.order_by(RequirementTemplate.sort_order, RequirementTemplate.id).all()


@router.post("/requirements", response_model=RequirementTemplateResponse, status_code=201)
def create_requirement_template(
    data: RequirementTemplateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    dup_q = db.query(RequirementTemplate).filter(
        RequirementTemplate.label == data.label,
        RequirementTemplate.is_active == True,
    )
    if data.hauler_type:
        dup_q = dup_q.filter(RequirementTemplate.hauler_type == data.hauler_type)
    else:
        dup_q = dup_q.filter(RequirementTemplate.hauler_type.is_(None))
    if dup_q.first():
        raise HTTPException(400, f"Requirement '{data.label}' already exists for scope '{data.hauler_type or 'global'}'")

    template = RequirementTemplate(
        label=data.label, description=data.description,
        is_required=data.is_required, sort_order=data.sort_order,
        hauler_type=data.hauler_type, is_active=True, created_by=current_user.id,
    )
    db.add(template)
    db.commit()
    db.refresh(template)

    biz_q = db.query(BusinessRecord)
    if data.hauler_type:
        biz_q = biz_q.filter(BusinessRecord.hauler_type == data.hauler_type)
    for biz in biz_q.all():
        exists = db.query(RequirementSubmission).filter(
            RequirementSubmission.business_id == biz.id,
            RequirementSubmission.template_id == template.id,
        ).first()
        if not exists:
            db.add(RequirementSubmission(business_id=biz.id, template_id=template.id, is_submitted=False))
    db.commit()
    log_audit(db, current_user.id, "CREATE", "REQUIREMENT_TEMPLATE", template.id,
              {"label": template.label, "hauler_type": template.hauler_type})
    return template


@router.put("/requirements/{template_id}", response_model=RequirementTemplateResponse)
def update_requirement_template(
    template_id: int,
    data: RequirementTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    template = db.query(RequirementTemplate).filter(RequirementTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "Requirement template not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    template.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(template)
    log_audit(db, current_user.id, "UPDATE", "REQUIREMENT_TEMPLATE", template.id, {"label": template.label})
    return template


@router.delete("/requirements/{template_id}", status_code=204)
def delete_requirement_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    template = db.query(RequirementTemplate).filter(RequirementTemplate.id == template_id).first()
    if not template:
        raise HTTPException(404, "Requirement template not found")
    template.is_active = False
    template.updated_at = datetime.utcnow()
    db.commit()
    log_audit(db, current_user.id, "DELETE", "REQUIREMENT_TEMPLATE", template.id, {"label": template.label})
    return None


@router.post("/requirements/reorder")
def reorder_requirements(
    order: List[int],
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    for idx, tid in enumerate(order):
        t = db.query(RequirementTemplate).filter(RequirementTemplate.id == tid).first()
        if t:
            t.sort_order = idx + 1
    db.commit()
    return {"message": "Order updated"}


# ============================================================================
# BUSINESS LINES
# ============================================================================

@router.get("/business-lines")
def get_business_lines(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    setting = db.query(SystemSetting).filter(SystemSetting.key == "business_lines").first()
    if not setting or not setting.value:
        from app.utils.constants import BUSINESS_LINES
        return {"business_lines": BUSINESS_LINES}
    try:
        return {"business_lines": json.loads(setting.value)}
    except:
        from app.utils.constants import BUSINESS_LINES
        return {"business_lines": BUSINESS_LINES}


@router.put("/business-lines")
def update_business_lines(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    lines = payload.get("business_lines", [])
    if not lines:
        raise HTTPException(400, "At least one business line is required")
    _save_setting(db, "business_lines", "Business Lines", "general", lines, current_user.id)
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "business_lines"})
    return {"message": "Business lines updated", "count": len(lines)}


# ============================================================================
# EXEMPTED LINES
# ============================================================================

@router.get("/exempted-lines")
def get_exempted_lines(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    return {"exempted_lines": _load_setting(db, "exempted_business_lines", [])}


@router.put("/exempted-lines")
def update_exempted_lines(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    lines = payload.get("exempted_lines", [])
    _save_setting(db, "exempted_business_lines", "Exempted Business Lines", "requirements", lines, current_user.id)
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "exempted_business_lines"})
    return {"message": "Exempted lines updated", "count": len(lines)}


@router.get("/exempted-inspection-lines")
def get_exempted_inspection_lines(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    return {"exempted_inspection_lines": _load_setting(db, "exempted_inspection_lines", [])}


@router.put("/exempted-inspection-lines")
def update_exempted_inspection_lines(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    lines = payload.get("exempted_inspection_lines", [])
    _save_setting(db, "exempted_inspection_lines", "Exempted Business Lines (Inspection)", "inspection", lines, current_user.id)
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "exempted_inspection_lines"})
    return {"message": "Exempted inspection lines updated", "count": len(lines)}


# ============================================================================
# SIGNATORIES
# ============================================================================

_EMPTY_CLR_SIGS = {
    "recommending_name": "", "recommending_title": "", "recommending_signature": None,
    "approving_name": "", "approving_title": "", "approving_signature": None,
}

@router.get("/signatories")
def get_signatories(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    return _load_setting(db, "signatories", _EMPTY_CLR_SIGS)


@router.put("/signatories")
def update_signatories(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    existing = _load_setting(db, "signatories", _EMPTY_CLR_SIGS)
    existing.update(payload)
    _save_setting(db, "signatories", "Clearance Signatories", "clearance", existing, current_user.id)
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "signatories"})
    return {"message": "Signatories updated"}


_EMPTY_RPT_SIGS = {
    "certified_by_name": "", "certified_by_title": "", "certified_by_signature": None,
    "approved_by_name": "", "approved_by_title": "", "approved_by_signature": None,
}

@router.get("/report-signatories")
def get_report_signatories(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    return _load_setting(db, "report_signatories", _EMPTY_RPT_SIGS)


@router.put("/report-signatories")
def update_report_signatories(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    existing = _load_setting(db, "report_signatories", _EMPTY_RPT_SIGS)
    existing.update(payload)
    _save_setting(db, "report_signatories", "Report Signatories", "report", existing, current_user.id)
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "report_signatories"})
    return {"message": "Report signatories updated"}


# ============================================================================
# SIGNATURE UPLOAD
# ============================================================================

@router.post("/upload-signature")
async def upload_signature(
    file: UploadFile = File(...),
    sig_type: str = Form("clearance"),
    role: str = Form("recommending"),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    if not (file.filename or "").lower().endswith(".png") and file.content_type != "image/png":
        raise HTTPException(400, "Only PNG files are accepted")
    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(400, "Signature file too large (max 2MB)")

    filename = f"{sig_type}_{role}_{int(datetime.utcnow().timestamp())}.png"
    with open(SIGNATURE_DIR / filename, "wb") as f:
        f.write(contents)

    data_url = f"data:image/png;base64,{base64.b64encode(contents).decode()}"

    key = "signatories" if sig_type == "clearance" else "report_signatories"
    default = _EMPTY_CLR_SIGS if sig_type == "clearance" else _EMPTY_RPT_SIGS
    existing = _load_setting(db, key, default)
    existing[f"{role}_signature"] = data_url
    _save_setting(db, key, key.replace("_", " ").title(), sig_type, existing, current_user.id)

    return {"url": data_url, "filename": filename}


# ============================================================================
# ADMIN ACCOUNT MANAGEMENT
# ============================================================================

@router.get("/admin-account")
def get_admin_info(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    """Return current active admin's basic info (no password)."""
    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        return {"admin": None}

    admin = db.query(User).filter(
        User.role_id == admin_role.id,
        User.is_active == True,
    ).first()

    if not admin:
        return {"admin": None}

    return {
        "admin": {
            "id": admin.id,
            "email": admin.email,
            "full_name": admin.full_name,
            "created_at": admin.created_at.isoformat() if admin.created_at else None,
        }
    }


@router.get("/admin-account/all")
def get_all_admin_accounts(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    """Get all admin accounts (including inactive ones) - useful for restore/transfer."""
    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        return {"admins": []}
    
    admins = db.query(User).filter(User.role_id == admin_role.id).order_by(User.created_at.desc()).all()
    
    return {
        "admins": [
            {
                "id": a.id,
                "email": a.email,
                "full_name": a.full_name,
                "is_active": a.is_active,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in admins
        ]
    }


@router.get("/admin-account/deactivated")
def get_deactivated_admins(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    """Get all deactivated admin accounts (for restore/transfer)."""
    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        return {"admins": []}
    
    deactivated = db.query(User).filter(
        User.role_id == admin_role.id,
        User.is_active == False,
    ).order_by(User.created_at.desc()).all()
    
    return {
        "admins": [
            {
                "id": a.id,
                "email": a.email,
                "full_name": a.full_name,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "deactivated_at": a.updated_at.isoformat() if a.updated_at else None,
            }
            for a in deactivated
        ]
    }


@router.post("/admin-account")
def create_new_admin(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """
    Create a new admin account OR restore an existing deactivated admin account.
    
    If an account with the given email already exists (even if deactivated),
    it will be reactivated instead of creating a new one.
    """
    email = (payload.get("email") or "").strip().lower()
    full_name = (payload.get("full_name") or "").strip()

    if not email:
        raise HTTPException(400, "Email is required")
    if not full_name:
        raise HTTPException(400, "Full name is required")

    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        raise HTTPException(500, "Admin role not found in database")

    # Check if an admin account with this email already exists
    existing_admin = db.query(User).filter(
        User.email == email,
        User.role_id == admin_role.id
    ).first()

    is_restore = existing_admin is not None
    generated_pw = _gen_password(8)
    hashed_password = get_password_hash(generated_pw)

    # Get current active admin
    old_admin = db.query(User).filter(
        User.role_id == admin_role.id,
        User.is_active == True,
    ).first()

    if is_restore:
        # RESTORE existing admin account
        existing_admin.is_active = True
        existing_admin.hashed_password = hashed_password
        existing_admin.full_name = full_name
        existing_admin.updated_at = datetime.utcnow()
        db.add(existing_admin)
        db.flush()
        new_admin = existing_admin
    else:
        # CREATE new admin account
        username = email.split('@')[0]
        base_username = username
        counter = 1
        while db.query(User).filter(User.username == username).first():
            username = f"{base_username}{counter}"
            counter += 1
        
        new_admin = User(
            username=username,
            email=email,
            full_name=full_name,
            hashed_password=hashed_password,
            role_id=admin_role.id,
            is_active=True,
            created_at=datetime.utcnow(),
            created_by=current_user.id,
        )
        db.add(new_admin)
        db.flush()

    # Deactivate previous admin(s) - but NOT if it's the same account being restored
    if old_admin and old_admin.id != new_admin.id:
        db.query(User).filter(
            User.role_id == admin_role.id,
            User.is_active == True,
            User.id != new_admin.id,
        ).update({"is_active": False}, synchronize_session=False)

    db.commit()

    # Send email notifications
    email_sent = False
    email_error = None
    old_admin_notified = False

    # 1. Email the new/restored admin with credentials
    try:
        action_text = "restored" if is_restore else "created"
        send_email(
            to_email=email,
            subject=f"EMC System — Admin Account {action_text.upper()}",
            body=f"""
            <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
              <h2 style="color:#1a4a2e;">EMC System — Admin Account {action_text.capitalize()}</h2>
              <p>Hello <strong>{full_name}</strong>,</p>
              <p>Your administrator account has been {action_text} in the
                 Environmental Management Clearance System.</p>
              <table style="border-collapse:collapse;width:100%;margin:16px 0;
                            background:#f0fdf4;border:1px solid #dcfce7;">
                  <tr>
                  <td style="padding:12px;font-weight:bold;">Email</td>
                  <td style="padding:12px;">{email}</td>
                  </tr>
                <tr style="background:#fff3e0;">
                  <td style="padding:12px;font-weight:bold;">Temporary Password</td>
                  <td style="padding:12px;font-family:monospace;
                             font-size:16px;letter-spacing:2px;">{generated_pw}</td>
                  </tr>
                </table>
              <p style="color:#dc2626;font-size:13px;">
                <strong>Important:</strong> Please change your password immediately
                after your first login.
              </p>
              <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
              <p style="color:#999;font-size:12px;">
                City Environment and Natural Resources Office · Tagaytay City
              </p>
            </div>
            """,
        )
        email_sent = True
    except Exception as e:
        email_error = str(e)

    # 2. Email the previous admin to notify them access has been revoked (if different)
    if old_admin and old_admin.id != new_admin.id and old_admin.email:
        try:
            send_email(
                to_email=old_admin.email,
                subject="EMC System — Admin Access Transferred",
                body=f"""
                <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
                  <h2 style="color:#7f1d1d;">EMC System — Your Admin Access Has Been Revoked</h2>
                  <p>Hello <strong>{old_admin.full_name}</strong>,</p>
                  <p>This is to inform you that your administrator access to the
                     <strong>Environmental Management Clearance System</strong> has been
                     transferred to another account.</p>
                  <div style="background:#fef2f2;border:1px solid #fecaca;
                              border-radius:8px;padding:16px;margin:16px 0;">
                    <p style="margin:0;color:#991b1b;font-size:14px;">
                      <strong>Your account is now deactivated.</strong><br>
                      New admin email: <strong>{email}</strong>
                    </p>
                  </div>
                  <p style="color:#666;font-size:13px;">
                    If you did not authorise this change, please contact the
                    CENRO office immediately.
                  </p>
                  <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
                  <p style="color:#999;font-size:12px;">
                    City Environment and Natural Resources Office · Tagaytay City
                  </p>
                </div>
                """,
            )
            old_admin_notified = True
        except Exception as e:
            pass

    # Log audit
    log_audit(
        db, current_user.id, "CREATE" if not is_restore else "RESTORE", "ADMIN_ACCOUNT", new_admin.id,
        {
            "action": "restored" if is_restore else "created",
            "email": email,
            "deactivated_previous": bool(old_admin and old_admin.id != new_admin.id),
            "old_admin_email": old_admin.email if old_admin and old_admin.id != new_admin.id else None,
            "old_admin_notified": old_admin_notified,
            "new_admin_email_sent": email_sent,
        },
    )

    response_data = {
        "message": f"Admin account {'restored' if is_restore else 'created'} for {email}.",
        "email": email,
        "full_name": full_name,
        "email_sent": email_sent,
        "old_admin_notified": old_admin_notified,
        "is_restore": is_restore,
    }

    if not email_sent:
        response_data["temporary_password"] = generated_pw
        response_data["email_error"] = email_error
        response_data["warning"] = (
            "Email delivery failed. Please copy the temporary password below "
            "and provide it to the admin manually."
        )

    return response_data


@router.post("/admin-account/activate/{admin_id}")
def activate_admin_account(
    admin_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    """
    Activate a previously deactivated admin account.
    This will deactivate the current admin and activate the selected one.
    """
    admin_role = db.query(Role).filter(Role.name == "admin").first()
    if not admin_role:
        raise HTTPException(500, "Admin role not found")

    target_admin = db.query(User).filter(
        User.id == admin_id,
        User.role_id == admin_role.id
    ).first()

    if not target_admin:
        raise HTTPException(404, "Admin account not found")

    if target_admin.is_active:
        raise HTTPException(400, "This admin account is already active")

    # Get current active admin
    current_active = db.query(User).filter(
        User.role_id == admin_role.id,
        User.is_active == True,
    ).first()

    # Deactivate current admin
    if current_active:
        current_active.is_active = False
        db.add(current_active)

    # Activate target admin
    target_admin.is_active = True
    target_admin.updated_at = datetime.utcnow()
    db.add(target_admin)
    db.commit()

    log_audit(
        db, current_user.id, "ACTIVATE", "ADMIN_ACCOUNT", target_admin.id,
        {
            "activated_email": target_admin.email,
            "deactivated_email": current_active.email if current_active else None,
        },
    )

    return {
        "message": f"Admin account {target_admin.email} activated. Previous admin deactivated.",
        "activated": {
            "id": target_admin.id,
            "email": target_admin.email,
            "full_name": target_admin.full_name,
        }
    }


@router.get("/inspection-frequency")
def get_inspection_frequency(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    setting = db.query(SystemSetting).filter(SystemSetting.key == "inspection_frequency").first()
    if not setting or not setting.value:
        return {"frequency": 1, "period": "year"}
    try:
        return json.loads(setting.value)
    except:
        return {"frequency": 1, "period": "year"}

@router.put("/inspection-frequency")
def update_inspection_frequency(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    _save_setting(db, "inspection_frequency", "Inspection Frequency", "inspection", payload, current_user.id)
    log_audit(db, current_user.id, "UPDATE", "SETTING", None, {"key": "inspection_frequency"})
    return {"message": "Inspection frequency updated", **payload}
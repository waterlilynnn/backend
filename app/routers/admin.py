from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
import secrets
import string

from app.core.database import get_db
from app.core.security import admin_only, get_password_hash, log_audit
from app.models.user import User
from app.models.role import Role
from app.schemas.user import StaffCreate, UserResponse
from app.utils.email import send_email

MAX_ACTIVE_STAFF = 5

router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)


def generate_random_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def send_staff_credentials_email(to_email: str, full_name: str, temp_password: str, action: str) -> bool:
    """
    FIX: shared helper to email staff their login credentials.
    `action` is either "created" or "reset" — used for subject/body wording.
    Mirrors the styling used for admin account emails (see routers/users
    and routers/archive) so all account-credential emails look consistent.
    """
    action_label = "Created" if action == "created" else "Password Reset"
    intro = (
        "Your staff account has been created in the Environmental Management Clearance System."
        if action == "created"
        else "Your password has been reset by an administrator in the Environmental Management Clearance System."
    )

    return send_email(
        to_email=to_email,
        subject=f"EMC System — Staff Account {action_label}",
        body=f"""
        <div style="font-family:sans-serif;max-width:480px;margin:0 auto;">
          <h2 style="color:#1a4a2e;">EMC System — Staff Account {action_label}</h2>
          <p>Hello <strong>{full_name}</strong>,</p>
          <p>{intro}</p>
          <table style="border-collapse:collapse;width:100%;margin:16px 0;
                        background:#f0fdf4;border:1px solid #dcfce7;">
            <tr>
              <td style="padding:12px;font-weight:bold;">Email</td>
              <td style="padding:12px;">{to_email}</td>
            </tr>
            <tr style="background:#fff3e0;">
              <td style="padding:12px;font-weight:bold;">Temporary Password</td>
              <td style="padding:12px;font-family:monospace;
                         font-size:16px;letter-spacing:2px;">{temp_password}</td>
            </tr>
          </table>
          <p style="color:#dc2626;font-size:13px;">
            <strong>Important:</strong> Please change your password immediately
            after logging in.
          </p>
          <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
          <p style="color:#999;font-size:12px;">
            City Environment and Natural Resources Office · Tagaytay City
          </p>
        </div>
        """,
    )


@router.post("/staff", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_staff(
    staff_data: StaffCreate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_only)
):
    """Admin creates new staff account. Max 5 active staff allowed."""

    # Duplicate check
    existing = db.query(User).filter(User.email == staff_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    staff_role = db.query(Role).filter(Role.name == "staff").first()
    if not staff_role:
        raise HTTPException(status_code=500, detail="Staff role not found")

    # Active-staff limit
    active_count = db.query(User).filter(
        User.role_id == staff_role.id,
        User.is_active == True,
    ).count()

    if active_count >= MAX_ACTIVE_STAFF:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"STAFF_LIMIT_REACHED|{MAX_ACTIVE_STAFF}",
        )

    temp_password   = generate_random_password()
    hashed_password = get_password_hash(temp_password)
    username        = staff_data.email.split('@')[0]

    new_staff = User(
        username=username,
        full_name=staff_data.full_name,
        email=staff_data.email,
        hashed_password=hashed_password,
        role_id=staff_role.id,
        is_active=True,
        created_by=current_admin.id,
    )
    db.add(new_staff)
    db.commit()
    db.refresh(new_staff)

    # FIX: actually send the temporary password to the new staff member's email
    email_sent = send_staff_credentials_email(
        to_email=new_staff.email,
        full_name=new_staff.full_name,
        temp_password=temp_password,
        action="created",
    )

    log_audit(
        db, current_admin.id, "CREATE", "USER", new_staff.id,
        {"email": new_staff.email, "credentials_email_sent": email_sent},
    )

    print(f"\nNEW STAFF ACCOUNT CREATED")
    print(f"   Email: {new_staff.email}")
    print(f"   Temporary Password: {temp_password}")
    print(f"   Email sent: {email_sent}\n")

    return {
        "id":                 new_staff.id,
        "username":           new_staff.username,
        "full_name":          new_staff.full_name,
        "email":              new_staff.email,
        "role":               "staff",
        "is_active":          new_staff.is_active,
        "created_at":         new_staff.created_at,
        # FIX: only surface the temp password in the response when the
        # email failed to send — otherwise the admin doesn't need to
        # see/copy it, it's already in the staff member's inbox.
        "temporary_password": None if email_sent else temp_password,
        "email_sent":         email_sent,
    }


@router.get("/staff", response_model=List[UserResponse])
def get_all_staff(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_only)
):
    staff_role = db.query(Role).filter(Role.name == "staff").first()
    if not staff_role:
        return []

    members = db.query(User).filter(
        User.role_id == staff_role.id
    ).order_by(User.created_at.desc()).all()

    return [
        UserResponse(
            id=s.id,
            username=s.username,
            full_name=s.full_name,
            email=s.email,
            role="staff",
            is_active=s.is_active,
            created_at=s.created_at,
        )
        for s in members
    ]


@router.get("/staff/active-count")
def get_active_staff_count(
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_only),
):
    staff_role = db.query(Role).filter(Role.name == "staff").first()
    count = 0
    if staff_role:
        count = db.query(User).filter(
            User.role_id == staff_role.id,
            User.is_active == True,
        ).count()
    return {"active_count": count, "max_allowed": MAX_ACTIVE_STAFF}


@router.post("/staff/{staff_id}/reset-password")
def reset_staff_password(
    staff_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_only),
):
    staff = db.query(User).filter(User.id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    if staff.role.name != "staff":
        raise HTTPException(status_code=400, detail="User is not a staff member")

    temp_password   = generate_random_password()
    staff.hashed_password = get_password_hash(temp_password)
    db.commit()

    # FIX: email the new temporary password to the staff member
    email_sent = send_staff_credentials_email(
        to_email=staff.email,
        full_name=staff.full_name,
        temp_password=temp_password,
        action="reset",
    )

    log_audit(
        db, current_admin.id, "RESET_PASSWORD", "USER", staff.id,
        {"email": staff.email, "credentials_email_sent": email_sent},
    )

    response = {
        "message":  "Password reset successfully" if email_sent else
                     "Password reset successfully, but the email could not be sent.",
        "staff_id": staff.id,
        "email":    staff.email,
        "email_sent": email_sent,
    }

    # FIX: only include the raw temp password in the response if email failed,
    # so the admin can hand it over manually.
    if not email_sent:
        response["temporary_password"] = temp_password
        response["warning"] = (
            "Email delivery failed. Please copy the temporary password "
            "and provide it to the staff member manually."
        )

    return response


@router.patch("/staff/{staff_id}/toggle-status")
def toggle_staff_status(
    staff_id: int,
    db: Session = Depends(get_db),
    current_admin: User = Depends(admin_only),
):
    staff = db.query(User).filter(User.id == staff_id).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff not found")
    if staff.role.name != "staff":
        raise HTTPException(status_code=400, detail="User is not a staff member")

    staff_role = db.query(Role).filter(Role.name == "staff").first()

    if not staff.is_active:
        active_count = db.query(User).filter(
            User.role_id == staff_role.id,
            User.is_active == True,
        ).count()
        if active_count >= MAX_ACTIVE_STAFF:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Maximum of {MAX_ACTIVE_STAFF} active staff accounts allowed. Deactivate another staff member first.",
            )

    staff.is_active = not staff.is_active
    db.commit()

    log_audit(
        db, current_admin.id,
        "ACTIVATE" if staff.is_active else "DEACTIVATE",
        "USER", staff.id,
        {"email": staff.email, "is_active": staff.is_active},
    )

    return {
        "id":        staff.id,
        "is_active": staff.is_active,
    }
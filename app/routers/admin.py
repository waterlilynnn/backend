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

MAX_ACTIVE_STAFF = 5

router = APIRouter(
    prefix="/admin",
    tags=["Admin"]
)


def generate_random_password(length=10):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


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

    log_audit(db, current_admin.id, "CREATE", "USER", new_staff.id, {"email": new_staff.email})

    print(f"\nNEW STAFF ACCOUNT CREATED")
    print(f"   Email: {new_staff.email}")
    print(f"   Temporary Password: {temp_password}\n")

    return {
        "id":                 new_staff.id,
        "username":           new_staff.username,
        "full_name":          new_staff.full_name,
        "email":              new_staff.email,
        "role":               "staff",
        "is_active":          new_staff.is_active,
        "created_at":         new_staff.created_at,
        "temporary_password": temp_password,
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

    log_audit(db, current_admin.id, "RESET_PASSWORD", "USER", staff.id, {"email": staff.email})

    return {
        "message":            "Password reset successfully",
        "staff_id":           staff.id,
        "email":              staff.email,
        "temporary_password": temp_password,
    }


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
    
    # If trying to activate a staff member
    if not staff.is_active:
        active_count = db.query(User).filter(
            User.role_id == staff_role.id,
            User.is_active == True,
        ).count()
        
        if active_count >= MAX_ACTIVE_STAFF:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot activate. Maximum {MAX_ACTIVE_STAFF} active staff accounts reached. Please deactivate another staff member first.",
            )

    staff.is_active = not staff.is_active
    db.commit()

    log_audit(db, current_admin.id, "TOGGLE", "USER", staff.id, {"is_active": staff.is_active})

    return {
        "message":   f"Staff member {'activated' if staff.is_active else 'deactivated'} successfully",
        "user_id":   staff.id,
        "is_active": staff.is_active,
    }
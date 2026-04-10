from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload
from pydantic import BaseModel, EmailStr
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user, log_audit
from app.models.user import User

router = APIRouter(prefix="/users", tags=["Users"])


class ProfileUpdate(BaseModel):
    full_name: str
    email: EmailStr


@router.get("/")
def get_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    users = db.query(User).options(joinedload(User.role)).all()
    
    # Convert to response format with role as string
    result = []
    for user in users:
        result.append({
            "id": user.id,
            "username": user.username,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role.name if user.role else "unknown",
            "is_active": user.is_active,
            "created_at": user.created_at,
        })
    
    return result


@router.post("/logout")
def logout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Log out user and record in audit log"""
    log_audit(
        db, 
        current_user.id, 
        "LOGOUT", 
        "AUTH", 
        None, 
        {"email": current_user.email, "full_name": current_user.full_name}
    )
    db.commit()
    return {"message": "Logged out successfully"}


@router.put("/profile")
def update_profile(
    data: ProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update current user's profile (name and email)"""
    
    # Check if email is already taken by another user
    existing = db.query(User).filter(
        User.email == data.email,
        User.id != current_user.id
    ).first()
    
    if existing:
        raise HTTPException(status_code=400, detail="Email already in use by another account")
    
    old_name = current_user.full_name
    old_email = current_user.email
    
    current_user.full_name = data.full_name
    current_user.email = data.email
    db.commit()
    
    # Log the profile update
    changes = {}
    if old_name != data.full_name:
        changes["full_name"] = {"old": old_name, "new": data.full_name}
    if old_email != data.email:
        changes["email"] = {"old": old_email, "new": data.email}
    
    if changes:
        log_audit(
            db, current_user.id, "UPDATE_PROFILE", "USER",
            current_user.id, {"changes": changes}
        )
    
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "role": current_user.role.name if current_user.role else "unknown"
    }
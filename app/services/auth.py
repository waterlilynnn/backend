from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status
from app.models.user import User
from app.core.security import (
    verify_password, 
    get_password_hash, 
    create_access_token, 
    log_audit,
    needs_password_rehash
)
from app.schemas.auth import ChangePasswordRequest
from datetime import datetime


def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).options(joinedload(User.role)).filter(User.email == email).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active. Please contact administrator.",
        )

    user.last_login = datetime.utcnow()
    
    if needs_password_rehash(user.hashed_password):
        user.hashed_password = get_password_hash(password)
    
    db.commit()

    log_audit(
        db,
        user.id,
        "LOGIN",
        "AUTH",
        None,
        {"email": user.email, "full_name": user.full_name, "role": user.role.name if user.role else "unknown"}
    )

    token_data = {
        "sub": str(user.id),
        "role": user.role.name if user.role else "unknown",
        "tv": user.token_version or 0,
    }

    return create_access_token(token_data)


def change_password(
    data: ChangePasswordRequest,
    db: Session,
    current_user: User,
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    current_user.hashed_password = get_password_hash(data.new_password)

    if data.logout_other_devices:
        current_user.token_version = (current_user.token_version or 0) + 1

    db.commit()

    log_audit(
        db,
        current_user.id,
        "CHANGE_PASSWORD",
        "AUTH",
        None,
        {
            "email": current_user.email,
            "full_name": current_user.full_name,
            "logged_out_other_devices": bool(data.logout_other_devices),
        },
    )

    token_data = {
        "sub": str(current_user.id),
        "role": current_user.role.name if current_user.role else "unknown",
        "tv": current_user.token_version or 0,
    }
    new_token = create_access_token(token_data)

    message = "Password changed successfully"
    if data.logout_other_devices:
        message += ". You have been logged out of all other devices/browsers."

    return {
        "message": message,
        "access_token": new_token,
        "token_type": "bearer",
    }
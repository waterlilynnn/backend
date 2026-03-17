from sqlalchemy.orm import Session, joinedload
from fastapi import HTTPException, status, Depends  
from app.models.user import User
from app.core.security import verify_password, get_password_hash, create_access_token, get_current_user
from app.utils.email import send_email
from app.schemas.user import StaffCreate  
from app.schemas.auth import ChangePasswordRequest  

def authenticate_user(db: Session, email: str, password: str):
    user = db.query(User).options(joinedload(User.role)).filter(User.email == email).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not active."
        )
    
    token_data = {
        "sub": str(user.id),
        "role": user.role.name if user.role else "unknown"
    }
    
    return create_access_token(token_data)

def change_password(
    data: ChangePasswordRequest, 
    db: Session,
    current_user: User
):
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    current_user.hashed_password = get_password_hash(data.new_password)
    db.commit()
    
    return {"message": "Password changed successfully"}

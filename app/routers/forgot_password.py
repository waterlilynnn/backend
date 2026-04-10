from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from datetime import datetime, timedelta
import random
import string

from app.core.database import get_db
from app.core.security import get_password_hash
from app.models.user import User
from app.models.verification_code import VerificationCode
from app.utils.email import send_email

router = APIRouter(prefix="/auth", tags=["Authentication"])

CODE_EXPIRE_MINUTES = 15

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

class VerifyCodeRequest(BaseModel):
    email: EmailStr
    code: str

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    code: str
    new_password: str

def generate_verification_code() -> str:
    return ''.join(random.choices(string.digits, k=6))

def send_verification_email(to_email: str, code: str, full_name: str):
    body = f"""
    <div style="font-family: sans-serif; max-width: 480px; margin: 0 auto;">
      <h2 style="color: #1a4a2e;">EMC System — Password Reset Code</h2>
      <p>Hi <strong>{full_name}</strong>,</p>
      <p>We received a request to reset your password.</p>
      <div style="background: #f0fdf4; border: 1px solid #dcfce7; border-radius: 12px; padding: 16px; text-align: center; margin: 20px 0;">
        <p style="font-size: 14px; color: #166534; margin-bottom: 8px;">Your verification code is:</p>
        <p style="font-size: 32px; font-weight: bold; letter-spacing: 8px; color: #065f46; font-family: sans-serif;">{code}</p>
      </div>
      <p style="color: #666; font-size: 13px;">
        This code will expire in <strong>{CODE_EXPIRE_MINUTES} minutes</strong>.
      </p>
      <p style="color: #999; font-size: 12px; margin-top: 24px;">
        If you did not request this, please ignore this email.
      </p>
      <hr style="border:none;border-top:1px solid #eee;margin:24px 0;">
      <p style="color:#999;font-size:12px;">City Environment and Natural Resources Office · Tagaytay City</p>
    </div>
    """
    send_email(to_email=to_email, subject="EMC System — Password Reset Code", body=body)

def cleanup_expired_codes(db: Session):
    db.query(VerificationCode).filter(VerificationCode.expires_at < datetime.utcnow()).delete()
    db.commit()

@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    cleanup_expired_codes(db)
    
    user = db.query(User).filter(User.email == data.email, User.is_active == True).first()
    
    if user:
        old_codes = db.query(VerificationCode).filter(VerificationCode.email == data.email, VerificationCode.is_used == False).all()
        for old in old_codes:
            old.is_used = True
        db.commit()
        
        code = generate_verification_code()
        expires_at = datetime.utcnow() + timedelta(minutes=CODE_EXPIRE_MINUTES)
        
        verification = VerificationCode(
            email=user.email,
            code=code,
            expires_at=expires_at,
            is_used=False
        )
        db.add(verification)
        db.commit()
        
        try:
            send_verification_email(user.email, code, user.full_name)
        except Exception as e:
            print(f"[forgot_password] Failed to send email: {e}")
    
    return {"message": "If an account with that email exists, a verification code has been sent."}

@router.post("/verify-code")
def verify_code(data: VerifyCodeRequest, db: Session = Depends(get_db)):
    cleanup_expired_codes(db)
    
    verification = db.query(VerificationCode).filter(
        VerificationCode.email == data.email,
        VerificationCode.code == data.code,
        VerificationCode.is_used == False,
        VerificationCode.expires_at > datetime.utcnow()
    ).first()
    
    if not verification:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    
    return {"message": "Code verified successfully"}

@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    if len(data.new_password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")
    
    cleanup_expired_codes(db)
    
    verification = db.query(VerificationCode).filter(
        VerificationCode.email == data.email,
        VerificationCode.code == data.code,
        VerificationCode.is_used == False,
        VerificationCode.expires_at > datetime.utcnow()
    ).first()
    
    if not verification:
        raise HTTPException(status_code=400, detail="Invalid or expired verification code")
    
    user = db.query(User).filter(User.email == data.email, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    user.hashed_password = get_password_hash(data.new_password)
    verification.is_used = True
    db.commit()
    
    return {"message": "Password reset successfully. You may now log in."}
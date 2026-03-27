from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta
from typing import List, Optional
from jose import jwt, JWTError
from fastapi.middleware.cors import CORSMiddleware
import json

from app.core.config import SECRET_KEY, ALGORITHM
from app.core.database import Base, engine, get_db
from app.core.security import create_access_token, get_current_user, staff_only, admin_only, log_audit
from app.schemas.user import UserResponse, LoginRequest, TokenResponse
from app.schemas.auth import ChangePasswordRequest
from app.schemas.business import (
    BusinessCreate, BusinessUpdate, BusinessResponse,
    BusinessSearchResponse, BusinessListResponse
)
from app.models.role import Role
from app.models.user import User
from app.models.business_record import BusinessRecord, HaulerType
from app.models.clearance import Clearance
from app.models.inspection import Inspection
from app.models.audit_log import AuditLog
from app.models.setting import SystemSetting

from app.routers import admin, clearance, business, inspections, bulk, audit, requirements, reports, settings
from app.services.auth import authenticate_user, change_password
from app.utils.constants import BARANGAYS, BUSINESS_LINES, HAULER_TYPES, PSIC_CATEGORIES
from app.utils.bin_validator import validate_bin_number

import traceback
import sys

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="EMC System Backend",
    description="Environmental Management Clearance System",
    version="1.0.0"
)

# Include routers
app.include_router(admin.router)
app.include_router(clearance.router)
app.include_router(business.router)
app.include_router(inspections.router)
app.include_router(bulk.router)
app.include_router(audit.router)
app.include_router(requirements.router)
app.include_router(reports.router)
app.include_router(settings.router)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {"message": "EMC System Backend running", "version": "1.0.0"}

@app.post("/login", response_model=TokenResponse, tags=["Authentication"])
def login(data: LoginRequest, db: Session = Depends(get_db)):
    try:
        token = authenticate_user(db, data.email, data.password)
        return {"access_token": token, "token_type": "bearer"}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/auth/change-password", tags=["Authentication"])
def change_password_endpoint(
    data: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return change_password(data, db, current_user)

@app.get("/users", response_model=List[UserResponse], tags=["Users"])
def get_users(db: Session = Depends(get_db), current_user: User = Depends(admin_only)):
    users = db.query(User).options(joinedload(User.role)).all()
    return users

@app.get("/options/barangays", tags=["Options"])
def get_barangays():
    return {"barangays": BARANGAYS}

@app.get("/options/business-lines", tags=["Options"])
def get_business_lines():
    return {"business_lines": BUSINESS_LINES}

@app.get("/options/hauler-types", tags=["Options"])
def get_hauler_types():
    return {"hauler_types": HAULER_TYPES}

@app.get("/options/psic-categories", tags=["Options"])
def get_psic_categories():
    return {"psic_categories": PSIC_CATEGORIES}

@app.post("/validate-bin", tags=["Options"])
def validate_bin(bin_number: str, db: Session = Depends(get_db)):
    """Validate BIN number against admin-configured formats."""
    # Fetch current formats from DB
    setting = db.query(SystemSetting).filter(SystemSetting.key == "bin_formats").first()
    formats_json = setting.value if setting else None

    is_valid, error_message = validate_bin_number(bin_number, formats_json)
    return {
        "valid": is_valid,
        "message": error_message or "Valid BIN number format"
    }

# Debug endpoints ( for development only, must be removed in production)
@app.get("/debug/check-user/{email}")
def debug_check_user(email: str, db: Session = Depends(get_db)):
    user = db.query(User).options(joinedload(User.role)).filter(User.email == email).first()
    if not user:
        return {"error": "User not found"}
    return {
        "exists": True,
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.name if user.role else "No role",
        "is_active": user.is_active
    }

@app.get("/debug/test-db", tags=["Debug"])
def test_database_connection(db: Session = Depends(get_db)):
    try:
        return {
            "database_status": "connected",
            "roles_count": db.query(Role).count(),
            "users_count": db.query(User).count(),
            "businesses_count": db.query(BusinessRecord).count(),
            "clearances_count": db.query(Clearance).count(),
            "inspections_count": db.query(Inspection).count(),
            "audit_logs_count": db.query(AuditLog).count(),
        }
    except Exception as e:
        return {"database_status": "error", "error": str(e)}

@app.exception_handler(Exception)
async def debug_exception_handler(request, exc):
    print(f"ERROR: {str(exc)}")
    traceback.print_exc(file=sys.stdout)
    return JSONResponse(status_code=500, content={"detail": str(exc)})
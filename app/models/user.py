from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class User(Base):
    __tablename__ = "tbl_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    email = Column(String(150), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    
    is_active = Column(Boolean, default=True)
    role_id = Column(Integer, ForeignKey("tbl_roles.id"), nullable=False)
    
    last_login = Column(DateTime, nullable=True)
    login_attempts = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(Integer, ForeignKey("tbl_users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    role = relationship("Role", lazy='joined')
    creator = relationship("User", remote_side=[id])
    
    # Track created records 
    created_businesses = relationship(
        "BusinessRecord", 
        foreign_keys="BusinessRecord.created_by",
        back_populates="creator_user"
    )
    
    # Track approvals
    approved_businesses = relationship(
        "BusinessRecord", 
        foreign_keys="BusinessRecord.approved_by",
        back_populates="approver_user"
    )
    
    # Track inspections
    inspections = relationship(
        "Inspection", 
        foreign_keys="Inspection.inspector_id",
        back_populates="inspector"
    )
    
    # Track prints
    printed_clearances = relationship(
        "Clearance", 
        foreign_keys="Clearance.printed_by",
        back_populates="printer_user"
    )
    
    last_printed_clearances = relationship(
        "Clearance", 
        foreign_keys="Clearance.last_printed_by",
        back_populates="last_printer_user"
    )
    
    # Audit logs
    audit_logs = relationship(
        "AuditLog", 
        foreign_keys="AuditLog.user_id",
        back_populates="user"
    )
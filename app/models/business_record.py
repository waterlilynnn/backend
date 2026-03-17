from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Date, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
import enum

class HaulerType(str, enum.Enum):
    CITY = "City"
    BARANGAY = "Barangay"
    ACCREDITED = "Accredited"
    HAZARDOUS = "Hazardous"
    EXEMPTED = "Exempted"
    NO_CONTRACT = "No Contract"

class ApplicationType(str, enum.Enum):
    NEW = "NEW"
    RENEWAL = "RENEWAL"

class BusinessRecord(Base):
    __tablename__ = "tbl_business"

    id = Column(Integer, primary_key=True)
    
    # Business Information
    bin_number = Column(String(50), index=True, nullable=True)
    establishment_name = Column(String(200), nullable=False)
    business_line = Column(String(150), nullable=False)
    
    # Owner Information
    owner_name_raw = Column(String(255), nullable=True)
    owner_last_name = Column(String(100), nullable=True)
    owner_first_name = Column(String(100), nullable=True)
    owner_middle_name = Column(String(100), nullable=True)
    owner_suffix = Column(String(50), nullable=True)
    
    # Contact
    contact_number = Column(String(20), nullable=True)
    email = Column(String(150), nullable=True)
    
    # Location
    location = Column(String(255), nullable=True)  
    has_own_structure = Column(Boolean, default=False)
    
    # Classification
    hauler_type = Column(Enum(HaulerType), nullable=False)
    
    # Application Details
    application_date = Column(DateTime, default=datetime.utcnow)
    application_type = Column(Enum(ApplicationType), default=ApplicationType.NEW)
    
    # Status
    status = Column(String(20), default="Pending")
    
    # Clearance Info
    control_number = Column(String(50), unique=True, nullable=True)
    date_issued = Column(Date, nullable=True)
    validity = Column(Date, nullable=True)
    sticker_color = Column(String(50), nullable=True)
    
    # QR Code (optional) 
    qr_code_url = Column(String(500), nullable=True)
    
    # Violation Tracking
    has_violation = Column(Boolean, default=False)
    violation_date = Column(Date, nullable=True)
    violation_details = Column(Text, nullable=True)
    violation_status = Column(String(20), default="None")
    
    # Revocation Tracking
    is_revoked = Column(Boolean, default=False)
    revoked_date = Column(Date, nullable=True)
    revoked_reason = Column(Text, nullable=True)
    reissued_date = Column(Date, nullable=True)
    
    # Audit Fields
    created_by = Column(Integer, ForeignKey("tbl_users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    approved_by = Column(Integer, ForeignKey("tbl_users.id"), nullable=True)
    approved_at = Column(DateTime, nullable=True)
    
    # For renewal tracking
    previous_record_id = Column(Integer, ForeignKey("tbl_business.id"), nullable=True)
    
    # Relationships
    creator_user = relationship("User", foreign_keys=[created_by], back_populates="created_businesses")
    approver_user = relationship("User", foreign_keys=[approved_by], back_populates="approved_businesses")
    previous_record = relationship("BusinessRecord", remote_side=[id])
    
    # Clearances
    clearances = relationship("Clearance", back_populates="business_record", cascade="all, delete-orphan")
    
    # Inspections
    inspections = relationship("Inspection", back_populates="business_record", cascade="all, delete-orphan")
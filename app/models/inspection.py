from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
import enum

class InspectionStatus(str, enum.Enum):
    PASSED = "PASSED"
    WITH_VIOLATION = "WITH VIOLATION"

class Inspection(Base):
    __tablename__ = "tbl_inspections"

    id = Column(Integer, primary_key=True)
    business_record_id = Column(Integer, ForeignKey("tbl_business.id"), nullable=False)
    inspector_id = Column(Integer, ForeignKey("tbl_users.id"), nullable=False)
    
    inspection_date = Column(DateTime, default=datetime.utcnow)
    status = Column(Enum(InspectionStatus), nullable=False)
    remarks = Column(Text, nullable=True)
    
    scanned_from_qr = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    business_record = relationship("BusinessRecord", back_populates="inspections")
    inspector = relationship("User", foreign_keys=[inspector_id], back_populates="inspections")
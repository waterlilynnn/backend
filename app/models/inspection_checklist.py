from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
 
 
class InspectionChecklist(Base):
    __tablename__ = "tbl_inspection_checklist"
 
    id            = Column(Integer, primary_key=True)
    inspection_id = Column(Integer, ForeignKey("tbl_inspections.id", ondelete="CASCADE"), nullable=False, unique=True)
 
    # DENR/LLDA Permits
    emb_ecc          = Column(String(20), nullable=True)
    emb_cnc          = Column(String(20), nullable=True)
    pamb_clearance   = Column(String(20), nullable=True)
    discharge_permit = Column(String(20), nullable=True)
 
    # City Permits
    sanitary_permit = Column(String(20), nullable=True)
    business_permit = Column(String(20), nullable=True)
 
    # Solid Waste Management Facility
    swm_facilities = Column(JSON, nullable=True)
 
    # Solid Waste Hauling 
    sw_hauling = Column(JSON, nullable=True)
 
    # Boolean fields
    has_iec_materials  = Column(Boolean, nullable=True)
    proper_segregation = Column(Boolean, nullable=True)
 
    # Wastewater Treatment 
    wwt_facilities = Column(JSON, nullable=True)
 
    # Desludging
    desludging       = Column(String(100), nullable=True)
    desludging_other = Column(String(255), nullable=True)
 
    # Violations 
    violations = Column(JSON, nullable=True)
 
    # Summary
    summary       = Column(String(255), nullable=True)
    summary_other = Column(String(255), nullable=True)
 
    # Recommendations
    recommendations       = Column(JSON, nullable=True)
    recommendations_other = Column(String(255), nullable=True)
 
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
 
    inspection = relationship("Inspection", back_populates="checklist")
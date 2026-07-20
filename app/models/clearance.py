from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Boolean, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base
import enum


class Clearance(Base):
    __tablename__ = "tbl_clearances"

    id                  = Column(Integer, primary_key=True)
    business_record_id  = Column(Integer, ForeignKey("tbl_business.id"), nullable=False)
    control_number      = Column(String(50), unique=True, nullable=False)

    # Clearance details
    clearance_color     = Column(String(20), nullable=False)
    valid_until         = Column(DateTime, nullable=False)

    # Printed by
    printed_by          = Column(Integer, ForeignKey("tbl_users.id"), nullable=False)
    printed_at          = Column(DateTime, default=datetime.utcnow)

    # PDF file
    pdf_filename        = Column(String(255), nullable=True)
    pdf_path            = Column(String(500), nullable=True)

    # Status
    is_active           = Column(Boolean, default=True)
    is_claimed          = Column(Boolean, default=False)
    claimed_at          = Column(DateTime, nullable=True)
    claimed_by          = Column(String(100), nullable=True)

    # Tracking
    print_count         = Column(Integer, default=1)
    last_printed_at     = Column(DateTime, default=datetime.utcnow)
    last_printed_by     = Column(Integer, ForeignKey("tbl_users.id"), nullable=True)
    
    is_archived         = Column(Boolean, default=False, nullable=False)
    archived_at         = Column(DateTime, nullable=True)
    archived_by         = Column(Integer, ForeignKey("tbl_users.id"), nullable=True)
    unarchived_at       = Column(DateTime, nullable=True)
    unarchived_by       = Column(Integer, ForeignKey("tbl_users.id"), nullable=True)

    created_at          = Column(DateTime, default=datetime.utcnow)

    # Relationships
    business_record    = relationship("BusinessRecord", back_populates="clearances")
    printer_user       = relationship("User", foreign_keys=[printed_by],      back_populates="printed_clearances")
    last_printer_user  = relationship("User", foreign_keys=[last_printed_by], back_populates="last_printed_clearances")
    archiver_user      = relationship("User", foreign_keys=[archived_by], back_populates="archived_clearances")
    unarchiver_user    = relationship("User", foreign_keys=[unarchived_by], back_populates="unarchived_clearances")
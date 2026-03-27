from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime,
    ForeignKey, Text
)
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class RequirementTemplate(Base):
    __tablename__ = "tbl_requirement_templates"

    id = Column(Integer, primary_key=True)
    label = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    is_required = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    hauler_type = Column(String(50), nullable=True)
    created_by = Column(Integer, ForeignKey("tbl_users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    submissions = relationship(
        "RequirementSubmission",
        back_populates="template",
        cascade="all, delete-orphan"
    )

class RequirementSubmission(Base):
    __tablename__ = "tbl_requirement_submissions"

    id = Column(Integer, primary_key=True)
    business_id = Column(Integer, ForeignKey("tbl_business.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(Integer, ForeignKey("tbl_requirement_templates.id", ondelete="CASCADE"), nullable=False)
    is_submitted = Column(Boolean, default=False)
    submitted_at = Column(DateTime, nullable=True)
    submitted_by = Column(Integer, ForeignKey("tbl_users.id"), nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    template = relationship("RequirementTemplate", back_populates="submissions")
    business = relationship("BusinessRecord", back_populates="requirement_submissions")
from sqlalchemy import Column, Integer, String, Boolean, DateTime
from sqlalchemy.dialects.mysql import LONGTEXT
from datetime import datetime
from app.core.database import Base


class SystemSetting(Base):
    __tablename__ = "tbl_settings"

    id         = Column(Integer, primary_key=True)
    key        = Column(String(100), unique=True, nullable=False, index=True)
    value      = Column(LONGTEXT, nullable=True)        
    label      = Column(String(200), nullable=True)
    category   = Column(String(50), nullable=False, default="general")
    is_active  = Column(Boolean, default=True)
    updated_by = Column(Integer, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
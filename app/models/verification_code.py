from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class VerificationCode(Base):
    __tablename__ = "tbl_verification_codes"

    id = Column(Integer, primary_key=True)
    email = Column(String(150), nullable=False, index=True)
    code = Column(String(10), nullable=False)
    is_used = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
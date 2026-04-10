from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from datetime import datetime
from app.core.database import Base

class AuditLog(Base):
    __tablename__ = "tbl_audit"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("tbl_users.id"), nullable=False)
    
    action = Column(String(50), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=True)
    
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", foreign_keys=[user_id], back_populates="audit_logs")
    
    __table_args__ = (
        Index('idx_audit_created_at', 'created_at'),
        Index('idx_audit_user_id', 'user_id'),
        Index('idx_audit_action', 'action'),
    )
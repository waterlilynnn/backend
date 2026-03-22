from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import datetime, date
import json

from app.core.database import get_db
from app.core.security import admin_only
from app.models.user import User
from app.models.audit_log import AuditLog
from app.models.business_record import BusinessRecord
from app.models.clearance import Clearance

router = APIRouter(
    prefix="/audit",
    tags=["Audit"]
)

def format_details(details_json, action, entity_type, entity_id, db):
    """Convert JSON details to readable plain text"""
    if not details_json:
        return "—"
    
    try:
        if isinstance(details_json, str):
            details = json.loads(details_json)
        else:
            details = details_json
        
        if entity_type == "USER":
            # Get user details
            user = db.query(User).filter(User.id == entity_id).first()
            user_display = f"{user.full_name} ({user.email})" if user else f"User ID: {entity_id}"
            
            if action == "CREATE":
                return f"CREATED staff account: {user_display}"
            
            elif action == "TOGGLE":
                is_active = details.get('is_active', False)
                status = 'ACTIVATED' if is_active else 'DEACTIVATED'
                return f"{status} staff account: {user_display}"
            
            elif action == "DELETE":
                email = details.get('email', 'Unknown')
                return f"DELETED staff account: {email}"
        
        elif entity_type == "BUSINESS":
            # Get business details
            business = db.query(BusinessRecord).filter(BusinessRecord.id == entity_id).first()
            business_name = business.establishment_name if business else f"Business ID: {entity_id}"
            
            if action == "CREATE":
                control = details.get('control_number', '')
                type_val = details.get('type', 'NEW')
                control_text = f" with control number {control}" if control else ""
                return f"CREATED business \"{business_name}\"{control_text} [{type_val}]"
            
            elif action == "UPDATE":
                changes = details.get('changes', {})
                if changes:
                    change_descs = []
                    for field, vals in changes.items():
                        field_name = field.replace('_', ' ').title()
                        old_val = vals.get('old', '—')
                        new_val = vals.get('new', '—')
                        
                        # Format specific fields
                        if field == 'has_violation':
                            old_val = 'Yes' if old_val == 'True' or old_val is True else 'No'
                            new_val = 'Yes' if new_val == 'True' or new_val is True else 'No'
                        
                        if field == 'establishment_name':
                            change_descs.append(f"name → \"{new_val}\" (from \"{old_val}\")")
                        elif field == 'business_line':
                            change_descs.append(f"business line → \"{new_val}\" (from \"{old_val}\")")
                        elif field == 'hauler_type':
                            change_descs.append(f"hauler type → {new_val} (from {old_val})")
                        elif field == 'application_type':
                            change_descs.append(f"application type → {new_val} (from {old_val})")
                        elif field == 'has_violation':
                            change_descs.append(f"violation status → {new_val} (from {old_val})")
                        else:
                            change_descs.append(f"{field_name} → {new_val} (from {old_val})")
                    
                    if change_descs:
                        return f"EDITED business \"{business_name}\": {', '.join(change_descs)}"
                return f"EDITED business \"{business_name}\""
            
            elif action == "DELETE":
                name = details.get('name', business_name)
                return f"DELETED business \"{name}\""
            
            elif action == "INSPECT":
                status = details.get('status', 'Unknown')
                return f"INSPECTED business \"{business_name}\": {status}"
        
        elif entity_type == "CLEARANCE":
            # Get clearance and business details
            clearance = db.query(Clearance).filter(Clearance.id == entity_id).first()
            if clearance:
                business = db.query(BusinessRecord).filter(BusinessRecord.id == clearance.business_record_id).first()
                business_name = business.establishment_name if business else "Unknown Business"
                control = clearance.control_number
            else:
                business_name = "Unknown Business"
                control = details.get('control_number', 'Unknown')
            
            if action == "GENERATE":
                return f"GENERATED clearance {control} for \"{business_name}\""
            
            elif action == "PRINT":
                return f"PRINTED clearance {control} for \"{business_name}\""
            
            elif action == "ISSUE":
                return f"ISSUED clearance {control} to \"{business_name}\""
        
        # Fallback
        if isinstance(details, dict):
            return f"{action}: {', '.join([f'{k}: {v}' for k, v in details.items()])}"
        return f"{action}: {str(details)}"
        
    except Exception as e:
        print(f"Error formatting details: {e}")
        return str(details_json)

@router.get("/logs")
def get_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    action: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only)
):
    query = db.query(AuditLog).options(
        joinedload(AuditLog.user)
    ).order_by(AuditLog.created_at.desc())
    
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id:
        query = query.filter(AuditLog.user_id == user_id)
    if date_from:
        query = query.filter(AuditLog.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(AuditLog.created_at <= datetime.combine(date_to, datetime.max.time()))
    
    total = query.count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    
    result_items = []
    for log in items:
        # Format details
        formatted_details = format_details(log.details, log.action, log.entity_type, log.entity_id, db)
        
        result_items.append({
            "id": log.id,
            "user": log.user.full_name if log.user else "System",
            "activity": formatted_details,
            "timestamp": log.created_at
        })
    
    return {
        "items": result_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page
    }
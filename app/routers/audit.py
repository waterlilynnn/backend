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
from app.models.inspection import Inspection

router = APIRouter(
    prefix="/audit",
    tags=["Audit"]
)

def format_details(details_json, action, entity_type, entity_id, db):
    if not details_json:
        return "—"
    
    try:
        if isinstance(details_json, str):
            details = json.loads(details_json)
        else:
            details = details_json
        
        if entity_type == "USER":
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
                        old_val = vals.get('old', '—')
                        new_val = vals.get('new', '—')
                        if field == 'has_violation':
                            old_val = 'Yes' if old_val in ('True', True) else 'No'
                            new_val = 'Yes' if new_val in ('True', True) else 'No'
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
                            change_descs.append(f"{field.replace('_', ' ').title()} → {new_val} (from {old_val})")
                    if change_descs:
                        return f"EDITED business \"{business_name}\": {', '.join(change_descs)}"
                return f"EDITED business \"{business_name}\""
            
            elif action == "DELETE":
                name = details.get('name', business_name)
                return f"DELETED business \"{name}\""
            
            elif action == "INSPECT":
                status = details.get('status', 'Unknown')
                return f"INSPECTED business \"{business_name}\": {status}"
            
            elif action == "RESOLVE":
                inspection_id = details.get('inspection_id', '—')
                resolved_remarks = details.get('resolved_remarks') or None
                remarks_text = f" · Remarks: {resolved_remarks}" if resolved_remarks and resolved_remarks != 'None' else ""
                return f"RESOLVED violation for \"{business_name}\" (Inspection #{inspection_id}){remarks_text}"
            
        elif entity_type == "CLEARANCE":
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
        
        elif entity_type == "REPORT":
            report_type = details.get("report_type", "unknown").capitalize()
            count = details.get("record_count", 0)
            filters = details.get("filters", {})
            active_filters = [f"{k}: {v}" for k, v in filters.items() if v and v != "all"]
            filter_text = f" [{', '.join(active_filters)}]" if active_filters else ""
            return f"EXPORTED {report_type} Report PDF — {count} record{'s' if count != 1 else ''}{filter_text}"
        
        elif entity_type == "REQUIREMENT_TEMPLATE":
            if action == "CREATE":
                return f"Added requirement: {details.get('label', 'Unknown')}"
            elif action == "UPDATE":
                return f"Updated requirement: {details.get('label', 'Unknown')}"
            elif action == "DELETE":
                return f"Removed requirement: {details.get('label', 'Unknown')}"
        
        elif entity_type == "SETTING":
            return f"Updated system setting: {details.get('key', 'Unknown')}"
        
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
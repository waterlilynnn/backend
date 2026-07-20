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
from app.models.requirement import RequirementTemplate

router = APIRouter(prefix="/audit", tags=["Audit"])


def _parse_details(details_raw):
    if details_raw is None:
        return {}
    if isinstance(details_raw, dict):
        return details_raw
    if isinstance(details_raw, str):
        try:
            return json.loads(details_raw)
        except Exception:
            return {}
    return {}


def format_activity(details_raw, action, entity_type, entity_id, db):
    """Format activity into simple readable string"""
    # Handle LOGIN/LOGOUT first — they may have empty details dict but should still get readable text
    if action in ("LOGIN", "LOGOUT"):
        return "Logged into the system" if action == "LOGIN" else "Logged out of the system"

    if not details_raw:
        return action

    try:
        details = _parse_details(details_raw)

        if entity_type == "USER":
            user = db.query(User).filter(User.id == entity_id).first() if entity_id else None
            user_display = f"{user.full_name} ({user.email})" if user else details.get("email", f"User ID: {entity_id}")

            if action == "CREATE":
                role = details.get("role", "staff")
                return f"Created new {role} account: {user_display}"
            elif action == "TOGGLE":
                is_active = details.get("is_active", False)
                state = "Activated" if is_active else "Deactivated"
                return f"{state} {user_display}"
            elif action == "RESET_PASSWORD":
                return f"Reset password for {user_display}"
            elif action == "DELETE":
                return f"Deleted account: {details.get('email', 'Unknown')}"
            elif action == "UPDATE_PROFILE":
                changes = details.get("changes", {})
                if "full_name" in changes:
                    return f"Updated name from '{changes['full_name']['old']}' to '{changes['full_name']['new']}'"
                elif "email" in changes:
                    return f"Updated email from '{changes['email']['old']}' to '{changes['email']['new']}'"
                return f"Updated profile information"
            else:
                return f"User account action: {action}"

        elif entity_type == "ADMIN_ACCOUNT":
            email = details.get("email", "Unknown")
            action_text = details.get("action", "modified")
            deactivated_previous = details.get("deactivated_previous", False)
            old_admin_email = details.get("old_admin_email")

            if action == "CREATE" and action_text == "created":
                if deactivated_previous and old_admin_email:
                    return f"Admin access transferred: New admin {email} created, previous admin ({old_admin_email}) deactivated"
                return f"Created new admin account: {email}"
            elif action == "RESTORE" or action_text == "restored":
                return f"Admin account restored: {email}"
            elif action == "ACTIVATE":
                activated_email = details.get("activated_email", email)
                deactivated_email = details.get("deactivated_email")
                if deactivated_email:
                    return f"Admin access transferred: {activated_email} activated, {deactivated_email} deactivated"
                return f"Activated admin account: {activated_email}"
            else:
                return f"Admin account modified: {email}"

        elif entity_type == "SETTING":
            key = details.get("key", "Unknown")
            labels = {
                "bin_formats": "Updated BIN number format settings",
                "business_lines": "Updated business lines list",
                "signatories": "Updated clearance signatories",
                "report_signatories": "Updated report signatories",
                "archive_settings": "Updated archive settings",
                "inspection_frequency": "Updated inspection frequency settings",
                "exempted_business_lines": "Updated exempted business lines",
                "exempted_inspection_lines": "Updated exempted inspection lines",
            }
            return labels.get(key, f"Updated system setting: {key}")

        elif entity_type == "REQUIREMENT_TEMPLATE":
            label = details.get("label", "Unknown")
            hauler = details.get("hauler_type")
            scope = f" for {hauler}" if hauler else ""

            if action == "CREATE":
                return f"Added requirement: {label}{scope}"
            elif action == "UPDATE":
                changes = details.get("changes", {})
                if "is_active" in changes:
                    new_status = changes.get("is_active", {}).get("new")
                    if new_status == False:
                        return f"Deactivated requirement: {label}{scope}"
                    elif new_status == True:
                        return f"Activated requirement: {label}{scope}"
                if "label" in changes:
                    return f"Renamed requirement from '{changes['label']['old']}' to '{changes['label']['new']}'"
                return f"Updated requirement: {label}{scope}"
            elif action == "DELETE":
                return f"Removed requirement: {label}{scope}"

        elif entity_type == "BUSINESS":
            business = db.query(BusinessRecord).filter(BusinessRecord.id == entity_id).first() if entity_id else None
            business_name = business.establishment_name if business else details.get("name", f"Business ID: {entity_id}")

            if action == "CREATE":
                return f"Created business record: {business_name}"
            elif action == "UPDATE":
                changes = details.get("changes", {})
                if changes:
                    changed_fields = list(changes.keys())
                    if len(changed_fields) == 1:
                        field = changed_fields[0].replace('_', ' ').title()
                        return f"Edited {field.lower()} of {business_name}"
                    else:
                        return f"Updated information for {business_name}"
                return f"Updated business record: {business_name}"
            elif action == "DELETE":
                return f"Deleted business record: {business_name}"
            elif action == "INSPECT":
                return f"Conducted inspection at: {business_name}"
            elif action == "RESOLVE":
                return f"Resolved violation for: {business_name}"
            elif action == "BULK_IMPORT":
                success = details.get("success", 0)
                return f"Bulk imported {success} business records"
            elif action == "UPDATE_REQUIREMENT":
                template_label = details.get("template_label", "requirement")
                is_submitted = details.get("is_submitted", False)
                action_word = "submitted" if is_submitted else "unsubmitted"
                return f"Marked '{template_label}' as {action_word} for {business_name}"
            else:
                return f"Business record action: {action}"

        elif entity_type == "CLEARANCE":
            clearance = db.query(Clearance).filter(Clearance.id == entity_id).first() if entity_id else None
            if clearance:
                business = db.query(BusinessRecord).filter(BusinessRecord.id == clearance.business_record_id).first()
                business_name = business.establishment_name if business else "Unknown Business"
            else:
                business_name = details.get("business_name", "Unknown Business")

            if action == "GENERATE":
                return f"Generated clearance for: {business_name}"
            elif action == "PRINT":
                return f"Downloaded clearance for: {business_name}"
            elif action == "ISSUE":
                return f"Issued clearance to: {business_name}"
            else:
                return f"Clearance action: {action}"

        elif entity_type == "REPORT":
            report_type = details.get("report_type", "unknown").capitalize()
            return f"Downloaded {report_type} report"

        elif action == "MANUAL_ARCHIVE":
            archived_count = details.get("archived_count", 0)
            return f"Manually archived {archived_count} record(s)"

        elif action == "ARCHIVE" and entity_type == "BUSINESS_RECORD":
            year = details.get("year")
            count = details.get("record_count", 0)
            if year:
                return f"Archived {count} record(s) from year {year}"
            return f"Archived {count} record(s)"

        elif action == "UNARCHIVE" and entity_type == "BUSINESS_RECORD":
            year = details.get("year")
            count = details.get("record_count", 0)
            if year:
                return f"Restored {count} archived record(s) from year {year}"
            return f"Restored {count} archived record(s)"

        if isinstance(details, dict) and details:
            return f"{action}: {', '.join(f'{k}: {v}' for k, v in details.items())}"

        return action

    except Exception as e:
        print(f"Error formatting audit details: {e}")
        return str(details_raw) if details_raw else action


@router.get("/logs")
def get_audit_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=1000),  # increased max for client-side filtering
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    user_id: Optional[int] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_only),
):
    query = (
        db.query(AuditLog)
        .options(joinedload(AuditLog.user))
        .order_by(AuditLog.created_at.desc())
    )

    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
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
        result_items.append({
            "id": log.id,
            "user_name": log.user.full_name if log.user else "System",
            "user_role": log.user.role.name if log.user and log.user.role else "System",
            "activity": format_activity(log.details, log.action, log.entity_type, log.entity_id, db),
            "timestamp": log.created_at,
            "action": log.action,
            "entity_type": log.entity_type,
        })

    return {
        "items": result_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": (total + per_page - 1) // per_page,
    }
from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import datetime, date
import os

from app.core.database import get_db
from app.core.security import staff_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord
from app.models.clearance import Clearance
from app.models.inspection import Inspection, InspectionStatus
from app.utils.report_pdf_generator import generate_report_pdf

router = APIRouter(
    prefix="/reports",
    tags=["Reports"]
)


def _fmt(d) -> str:
    if not d:
        return "—"
    try:
        if isinstance(d, (datetime, date)):
            return d.strftime("%m/%d/%Y %I:%M %p") if isinstance(d, datetime) else d.strftime("%m/%d/%Y")
        return datetime.fromisoformat(str(d)).strftime("%m/%d/%Y %I:%M %p")
    except Exception:
        return str(d)


@router.get("/clearances/download")
def download_clearances_pdf(
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[str] = Query(None),
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    query = db.query(Clearance).options(
        joinedload(Clearance.business_record),
        joinedload(Clearance.last_printer_user),
    )

    if date_from:
        query = query.filter(Clearance.printed_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Clearance.printed_at <= datetime.combine(date_to, datetime.max.time()))
    if status == "issued":
        query = query.filter(Clearance.is_claimed == True)
    elif status == "pending":
        query = query.filter(Clearance.is_claimed == False)

    clearances = query.order_by(Clearance.printed_at.desc()).all()

    if search:
        q = search.lower()
        clearances = [
            c for c in clearances
            if q in (c.control_number or "").lower()
            or q in (c.business_record.establishment_name if c.business_record else "").lower()
        ]

    if status == "issued":
        status_label = "Issued"
    elif status == "pending":
        status_label = "Pending"
    else:
        status_label = None

    # Add line breaks for long business names using <br/> in the cell text
    col_labels = ["Control #", "Business Name", "Hauler", "Last Downloaded", "Status"]
    rows = []
    for c in clearances:
        biz = c.business_record
        # Insert <br/> for long business names (>40 chars)
        name = biz.establishment_name if biz else "—"
        if len(name) > 40:
            # Find a space to break at ~40 chars
            break_pos = name[:40].rfind(' ')
            if break_pos == -1:
                break_pos = 40
            name = name[:break_pos] + "<br/>" + name[break_pos:].strip()
        
        rows.append([
            c.control_number or "—",
            name,
            (biz.hauler_type.value if hasattr(biz.hauler_type, "value") else str(biz.hauler_type)) if biz else "—",
            _fmt(c.last_printed_at or c.printed_at),
            "Issued" if c.is_claimed else "Pending",
        ])

    # Generate period label for report
    period_label = None
    if date_from and date_to:
        period_label = f"{date_from.strftime('%B %d, %Y')} - {date_to.strftime('%B %d, %Y')}"
    elif date_from:
        period_label = f"From {date_from.strftime('%B %d, %Y')}"
    elif date_to:
        period_label = f"Until {date_to.strftime('%B %d, %Y')}"

    filename = f"clearances_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_path = generate_report_pdf(
        report_title="Clearances Report",
        col_labels=col_labels,
        rows=rows,
        filename=filename,
        status_label=status_label,
        generated_by=current_user.full_name,
        period_label=period_label,
    )

    log_audit(
        db, current_user.id, "EXPORT", "REPORT",
        None, {
            "report_type": "clearances",
            "filters": {
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "status": status or "all",
                "search": search or None,
            },
            "record_count": len(rows),
        }
    )

    return FileResponse(
        path=pdf_path,
        filename=f"Clearances_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Clearances_Report_{datetime.now().strftime('%Y%m%d')}.pdf"},
    )


@router.get("/inspections/download")
def download_inspections_pdf(
    date_from:    Optional[date] = None,
    date_to:      Optional[date] = None,
    insp_status:  Optional[str]  = Query(None),
    hauler:       Optional[str]  = None,
    search:       Optional[str]  = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only),
):
    query = db.query(Inspection).options(
        joinedload(Inspection.business_record),
        joinedload(Inspection.inspector),
        joinedload(Inspection.resolver),
    )

    if date_from:
        query = query.filter(Inspection.inspection_date >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        query = query.filter(Inspection.inspection_date <= datetime.combine(date_to, datetime.max.time()))
    if insp_status == "passed":
        query = query.filter(Inspection.status == InspectionStatus.PASSED)
    elif insp_status == "unresolved":
        query = query.filter(
            Inspection.status == InspectionStatus.WITH_VIOLATION,
            Inspection.is_resolved == False,
        )
    elif insp_status == "resolved":
        query = query.filter(
            Inspection.status == InspectionStatus.WITH_VIOLATION,
            Inspection.is_resolved == True,
        )

    inspections = query.all()

    filtered = []
    for i in inspections:
        biz = i.business_record
        if hauler and hauler != "all":
            ht = biz.hauler_type.value if biz and hasattr(biz.hauler_type, "value") else (str(biz.hauler_type) if biz else "")
            if ht != hauler:
                continue
        if search:
            q = search.lower()
            name = biz.establishment_name.lower() if biz else ""
            bin_ = (biz.bin_number or "").lower() if biz else ""
            if q not in name and q not in bin_:
                continue
        filtered.append(i)

    unresolved = sorted(
        [i for i in filtered if i.status == InspectionStatus.WITH_VIOLATION and not i.is_resolved],
        key=lambda x: x.inspection_date or datetime.min,
    )
    rest = sorted(
        [i for i in filtered if not (i.status == InspectionStatus.WITH_VIOLATION and not i.is_resolved)],
        key=lambda x: x.inspection_date or datetime.min,
        reverse=True,
    )
    final = unresolved + rest

    if insp_status == "passed":
        status_label = "Passed"
    elif insp_status == "unresolved":
        status_label = "With Violation"
    elif insp_status == "resolved":
        status_label = "Resolved"
    else:
        status_label = None

    col_labels = ["Business Name", "BIN", "Hauler", "Inspector", "Date", "Result", "Remarks", "Resolved By", "Resolution Notes"]
    rows = []
    for i in final:
        biz    = i.business_record
        is_res = i.is_resolved
        result = "Passed" if i.status == InspectionStatus.PASSED else ("Resolved" if is_res else "With Violation")
        rows.append([
            biz.establishment_name if biz else "—",
            biz.bin_number or "—" if biz else "—",
            (biz.hauler_type.value if hasattr(biz.hauler_type, "value") else str(biz.hauler_type)) if biz else "—",
            i.inspector.full_name if i.inspector else "—",
            _fmt(i.inspection_date),
            result,
            i.remarks or "—",
            i.resolver.full_name if i.resolver else "—",
            i.resolved_remarks or "—",
        ])

    filename = f"inspections_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_path = generate_report_pdf(
        report_title="Inspections Report",
        col_labels=col_labels,
        rows=rows,
        filename=filename,
        status_label=status_label,
        use_landscape=True,
    )

    log_audit(
        db, current_user.id, "EXPORT", "REPORT",
        None, {
            "report_type": "inspections",
            "filters": {
                "date_from": str(date_from) if date_from else None,
                "date_to": str(date_to) if date_to else None,
                "status": insp_status or "all",
                "hauler": hauler or "all",
                "search": search or None,
            },
            "record_count": len(rows),
        }
    )

    return FileResponse(
        path=pdf_path,
        filename=f"Inspections_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=Inspections_Report_{datetime.now().strftime('%Y%m%d')}.pdf"},
    )
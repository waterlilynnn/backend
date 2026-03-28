from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.pdfgen import canvas as rl_canvas
from pathlib import Path
from datetime import datetime
from reportlab.lib.enums import TA_CENTER, TA_LEFT

UPLOAD_DIR = Path("uploads/reports")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

LOGOS_DIR = Path("app/assets/logos")
FRONTEND_PUBLIC = Path("../frontend/public")

PRIMARY = (0.078, 0.176, 0.431)
HEADER_COLOR = (0.11, 0.22, 0.48)


def find_asset(filename):
    for d in [LOGOS_DIR, FRONTEND_PUBLIC, Path("app/assets"), Path("public")]:
        p = d / filename
        if p.exists():
            return str(p)
    return None


def _draw_header(c, W, H, inner_m):
    bc = colors.Color(*PRIMARY)
    hc = colors.Color(*HEADER_COLOR)

    logo_size = 18 * mm
    logo_gap = 3 * mm
    logos_w = logo_size * 2 + logo_gap
    logos_x = (W - logos_w) / 2
    logo_y = H - inner_m - logo_size

    tl = find_asset("tagaytay-logo.png")
    if tl:
        c.drawImage(tl, logos_x, logo_y, width=logo_size, height=logo_size,
                    preserveAspectRatio=True, anchor='c', mask='auto')
    bp = find_asset("bp-logo.png")
    if bp:
        c.drawImage(bp, logos_x + logo_size + logo_gap, logo_y,
                    width=logo_size, height=logo_size,
                    preserveAspectRatio=True, anchor='c', mask='auto')

    t1_y = logo_y - 4.5 * mm
    t2_y = t1_y - 4.5 * mm
    t3_y = t2_y - 4.5 * mm

    c.setFillColor(hc)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawCentredString(W / 2, t1_y, "Republic of the Philippines")
    c.drawCentredString(W / 2, t2_y, "City Government of Tagaytay")
    c.drawCentredString(W / 2, t3_y, "CITY ENVIRONMENT AND NATURAL RESOURCES OFFICE")

    sep_y = t3_y - 3 * mm
    c.setStrokeColor(bc)
    c.setLineWidth(1.5)
    c.line(inner_m, sep_y, W - inner_m, sep_y)

    return sep_y


def _make_cell_style(font_size=8):
    return ParagraphStyle(
        'cell',
        fontName='Helvetica',
        fontSize=font_size,
        leading=font_size * 1.35,
        wordWrap='LTR',
        splitLongWords=True,
        alignment=TA_LEFT,
    )


def _make_header_style(font_size=8):
    return ParagraphStyle(
        'header_cell',
        fontName='Helvetica-Bold',
        fontSize=font_size,
        leading=font_size * 1.35,
        textColor=colors.white,
        wordWrap='LTR',
        alignment=TA_CENTER,
    )


def _draw_table_with_pagination(c, W, H, col_labels, rows, start_y, inner_m, font_size=8):
    """Draw table with pagination support"""
    table_w = W - 2 * inner_m
    col_count = len(col_labels)

    # Column width calculation
    wide_keywords = {'business', 'name', 'establishment', 'remarks', 'resolution', 'notes', 'line'}
    narrow_keywords = {'control', '#', 'bin', 'hauler', 'status', 'date', 'downloaded', 'inspector', 'result'}

    def get_col_type(label):
        label_lower = label.lower()
        if any(kw in label_lower for kw in wide_keywords):
            return 'wide'
        elif any(kw in label_lower for kw in narrow_keywords):
            return 'narrow'
        return 'medium'

    wide_count = sum(1 for l in col_labels if get_col_type(l) == 'wide')
    medium_count = sum(1 for l in col_labels if get_col_type(l) == 'medium')
    narrow_count = col_count - wide_count - medium_count

    base_w = table_w / (wide_count * 2 + medium_count * 1.2 + narrow_count * 0.8)
    col_widths = []
    for label in col_labels:
        ct = get_col_type(label)
        if ct == 'wide':
            col_widths.append(base_w * 2)
        elif ct == 'medium':
            col_widths.append(base_w * 1.2)
        else:
            col_widths.append(base_w * 0.8)

    cell_style = _make_cell_style(font_size - 0.5)
    header_style = _make_header_style(font_size)

    # Prepare all rows
    header_row = [Paragraph(str(h), header_style) for h in col_labels]
    data_rows = [
        [Paragraph(str(cell) if cell else '—', cell_style) for cell in row]
        for row in rows
    ]

    rows_per_page = int((start_y - inner_m - 45 * mm) / 7.5) 
    rows_per_page = max(5, min(rows_per_page, 25))  

    # Paginate
    total_pages = (len(data_rows) + rows_per_page - 1) // rows_per_page
    current_y = start_y

    for page_idx in range(total_pages):
        start_row = page_idx * rows_per_page
        end_row = min((page_idx + 1) * rows_per_page, len(data_rows))
        page_rows = data_rows[start_row:end_row]

        all_rows = [header_row] + page_rows
        tbl = Table(all_rows, colWidths=col_widths, repeatRows=1)

        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.black),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))

        avail_h = current_y - inner_m - 35 * mm
        tbl_w, tbl_h = tbl.wrap(table_w, avail_h)
        tbl.drawOn(c, inner_m, current_y - tbl_h)
        current_y = current_y - tbl_h - 5 * mm

        # Page number
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.gray)
        c.drawCentredString(W / 2, inner_m + 5 * mm, f"Page {page_idx + 1} of {total_pages}")

        # If not last page, create new page
        if page_idx < total_pages - 1:
            c.showPage()
            c.setFillColorRGB(1, 1, 1)
            c.rect(0, 0, W, H, fill=1, stroke=0)
            current_y = _draw_header(c, W, H, inner_m) - 20 * mm

    return current_y


def _draw_signature(c, W, H, inner_m, sig_name, sig_title, generated_by=None):
    """Draw signature with proper spacing"""
    hc = colors.Color(*HEADER_COLOR)

    sig_right = W - inner_m - 4 * mm
    sig_width = 60 * mm
    sig_left = sig_right - sig_width
    line_y = inner_m + 25 * mm
    name_y = line_y + 3 * mm
    title_y = line_y - 4 * mm
    by_y = line_y + 13 * mm

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    c.drawString(sig_left, by_y, "Approved/Certified by:")

    c.setFont("Helvetica-Bold", 9)
    c.setFillColor(hc)
    c.drawCentredString((sig_left + sig_right) / 2, name_y, sig_name)

    c.setStrokeColor(colors.black)
    c.setLineWidth(0.7)
    c.line(sig_left, line_y, sig_right, line_y)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.black)
    c.drawCentredString((sig_left + sig_right) / 2, title_y, sig_title)

    if generated_by:
        c.setFont("Helvetica", 7.5)
        c.setFillColor(colors.Color(0.5, 0.5, 0.5))
        c.drawString(inner_m, inner_m + 8 * mm, f"Generated by: {generated_by}")
        c.drawRightString(W - inner_m, inner_m + 8 * mm, f"Date: {datetime.now().strftime('%B %d, %Y %I:%M %p')}")


def generate_report_pdf(
    report_title: str,
    col_labels: list,
    rows: list,
    filename: str,
    status_label: str = None,
    sig_name: str = "OSCAR B. LAURENCIANA",
    sig_title: str = "OIC-CENRO",
    use_landscape: bool = False,
    generated_by: str = None,
    period_label: str = None,
) -> str:
    file_path = str(UPLOAD_DIR / filename)
    page_size = landscape(A4) if use_landscape else A4
    W, H = page_size
    inner_m = 16 * mm

    c = rl_canvas.Canvas(file_path, pagesize=page_size)

    # Draw first page
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    sep_y = _draw_header(c, W, H, inner_m)

    hc = colors.Color(*HEADER_COLOR)
    full_title = f"{report_title} — {status_label}" if status_label else report_title

    title_y = sep_y - 10 * mm
    c.setFillColor(hc)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W / 2, title_y, full_title.upper())

    meta_y = title_y - 6 * mm
    if period_label:
        c.setFont("Helvetica", 8.5)
        c.setFillColor(colors.Color(0.3, 0.3, 0.3))
        c.drawCentredString(W / 2, meta_y, f"Period: {period_label}")
        meta_base = meta_y - 6 * mm
    else:
        meta_base = title_y - 10 * mm

    # Date generated
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.black)
    date_str = datetime.now().strftime("%B %d, %Y  %I:%M %p")
    c.drawString(inner_m, meta_base, f"Date Generated: {date_str}")

    rule_y = meta_base - 3 * mm
    c.setStrokeColor(colors.Color(*PRIMARY))
    c.setLineWidth(0.5)
    c.line(inner_m, rule_y, W - inner_m, rule_y)

    table_start_y = rule_y - 3 * mm
    font_size = 7 if len(col_labels) > 7 else 8

    final_y = _draw_table_with_pagination(c, W, H, col_labels, rows, table_start_y, inner_m, font_size)

    if final_y > inner_m + 35 * mm:
        _draw_signature(c, W, H, inner_m, sig_name, sig_title, generated_by)
    else:
        # new page for signature if no space on last page
        c.showPage()
        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        _draw_header(c, W, H, inner_m)
        _draw_signature(c, W, H, inner_m, sig_name, sig_title, generated_by)

    c.save()
    return file_path
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import Table, TableStyle
from pathlib import Path
from datetime import datetime

UPLOAD_DIR = Path("uploads/reports")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

LOGOS_DIR       = Path("app/assets/logos")
FRONTEND_PUBLIC = Path("../frontend/public")

PRIMARY      = (0.078, 0.176, 0.431)
HEADER_COLOR = (0.11,  0.22,  0.48)


def find_asset(filename):
    for d in [LOGOS_DIR, FRONTEND_PUBLIC, Path("app/assets"), Path("public")]:
        p = d / filename
        if p.exists():
            return str(p)
    return None


def _draw_header(c, W, H, inner_m, b3):
    bc = colors.Color(*PRIMARY)
    hc = colors.Color(*HEADER_COLOR)

    logo_size = 18 * mm
    logo_gap  = 3  * mm
    logos_w   = logo_size * 2 + logo_gap
    logos_x   = (W - logos_w) / 2
    logo_y    = H - inner_m - logo_size

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
    t2_y = t1_y   - 4.5 * mm
    t3_y = t2_y   - 4.5 * mm

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


def _draw_table(c, W, col_labels, rows, start_y, inner_m, row_h=7*mm, font_size=8):
    col_count  = len(col_labels)
    table_w    = W - 2 * inner_m

    if col_count > 7:
        col_widths = []
        biz_idx = 0
        base_w = table_w / col_count
        for idx in range(col_count):
            if idx == biz_idx:
                col_widths.append(base_w * 1.8)
            else:
                remaining_w = (table_w - base_w * 1.8) / (col_count - 1)
                col_widths.append(remaining_w)
        total = sum(col_widths)
        col_widths = [w * table_w / total for w in col_widths]
    else:
        base_w = table_w / col_count
        biz_idx = next((i for i, l in enumerate(col_labels) if "business" in l.lower() or "name" in l.lower()), None)
        if biz_idx is not None:
            col_widths = [base_w] * col_count
            extra = base_w * 0.8
            col_widths[biz_idx] += extra
            shrink = extra / (col_count - 1)
            col_widths = [w - shrink if i != biz_idx else w for i, w in enumerate(col_widths)]
        else:
            col_widths = [base_w] * col_count

    all_rows = [col_labels] + rows
    tbl = Table(all_rows, colWidths=col_widths, rowHeights=row_h)
    tbl.setStyle(TableStyle([
        ('BACKGROUND',     (0, 0), (-1, 0), colors.black),
        ('TEXTCOLOR',      (0, 0), (-1, 0), colors.white),
        ('FONTNAME',       (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE',       (0, 0), (-1, 0), font_size),
        ('ALIGN',          (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN',         (0, 0), (-1,-1), 'MIDDLE'),
        ('FONTNAME',       (0, 1), (-1,-1), 'Helvetica'),
        ('FONTSIZE',       (0, 1), (-1,-1), font_size - 0.5),
        ('TEXTCOLOR',      (0, 1), (-1,-1), colors.black),
        ('ALIGN',          (0, 1), (-1,-1), 'LEFT'),
        ('ROWBACKGROUNDS', (0, 1), (-1,-1), [colors.white, colors.Color(0.95, 0.95, 0.95)]),
        ('GRID',           (0, 0), (-1,-1), 0.5, colors.black),
        ('LEFTPADDING',    (0, 0), (-1,-1), 3),
        ('RIGHTPADDING',   (0, 0), (-1,-1), 3),
        ('TOPPADDING',     (0, 0), (-1,-1), 2),
        ('BOTTOMPADDING',  (0, 0), (-1,-1), 2),
        ('WORDWRAP',       (0, 0), (-1,-1), True),
    ]))

    tbl_h = row_h * len(all_rows)
    tbl.wrapOn(c, table_w, tbl_h)
    tbl.drawOn(c, inner_m, start_y - tbl_h)
    return start_y - tbl_h


def _draw_signature(c, W, H, inner_m, sig_name, sig_title):
    hc = colors.Color(*HEADER_COLOR)

    sig_right = W - inner_m - 4*mm
    sig_width = 60 * mm
    sig_left  = sig_right - sig_width

    line_y = inner_m + 22 * mm
    name_y = line_y  +  3 * mm
    title_y = line_y -  4 * mm
    by_y   = line_y  + 13 * mm

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


def generate_report_pdf(
    report_title: str,
    col_labels: list,
    rows: list,
    filename: str,
    status_label: str = None,
    sig_name: str = "OSCAR B. LAURENCIANA",
    sig_title: str = "OIC-CENRO",
    use_landscape: bool = False,
) -> str:
    file_path = str(UPLOAD_DIR / filename)
    page_size = landscape(A4) if use_landscape else A4
    W, H = page_size

    inner_m = 16 * mm

    c = rl_canvas.Canvas(file_path, pagesize=page_size)

    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    sep_y = _draw_header(c, W, H, inner_m, None)

    hc = colors.Color(*HEADER_COLOR)

    if status_label:
        full_title = f"{report_title} — {status_label}"
    else:
        full_title = report_title

    title_y = sep_y - 10 * mm
    c.setFillColor(hc)
    c.setFont("Helvetica-Bold", 13)
    c.drawCentredString(W / 2, title_y, full_title.upper())

    meta_y = title_y - 10 * mm
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.black)
    date_str = datetime.now().strftime("%B %d, %Y  %I:%M %p")
    c.drawString(inner_m, meta_y, f"Date Generated: {date_str}")

    rule_y = meta_y - 3 * mm
    c.setStrokeColor(colors.Color(*PRIMARY))
    c.setLineWidth(0.5)
    c.line(inner_m, rule_y, W - inner_m, rule_y)

    table_start_y = rule_y - 3 * mm

    if len(col_labels) > 7:
        row_h, font_size = 6*mm, 7
    else:
        row_h, font_size = 7*mm, 8

    available_h = table_start_y - inner_m - 35*mm
    rows_per_page = max(1, int(available_h / row_h) - 1)

    page_num = 1
    remaining = rows[:]

    while True:
        chunk = remaining[:rows_per_page]
        remaining = remaining[rows_per_page:]

        end_y = _draw_table(c, W, col_labels, chunk, table_start_y, inner_m, row_h, font_size)

        c.setFont("Helvetica", 7)
        c.setFillColor(colors.gray)
        c.drawCentredString(W / 2, inner_m + 5*mm, f"Page {page_num}")

        if not remaining:
            _draw_signature(c, W, H, inner_m, sig_name, sig_title)
            break

        c.showPage()
        page_num += 1

        c.setFillColorRGB(1, 1, 1)
        c.rect(0, 0, W, H, fill=1, stroke=0)
        sep_y = _draw_header(c, W, H, inner_m, None)
        title_y = sep_y - 7 * mm
        c.setFillColor(colors.Color(*HEADER_COLOR))
        c.setFont("Helvetica-Bold", 13)
        c.drawCentredString(W / 2, title_y, full_title.upper())
        rule_y = title_y - 8 * mm
        c.setStrokeColor(colors.Color(*PRIMARY))
        c.setLineWidth(0.5)
        c.line(inner_m, rule_y, W - inner_m, rule_y)
        table_start_y = rule_y - 3 * mm

    c.save()
    return file_path
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums  import TA_JUSTIFY, TA_CENTER
from reportlab.platypus   import Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas
from datetime import datetime
from pathlib import Path
import base64
import io
from PIL import Image
import tempfile
import os

UPLOAD_DIR = Path("uploads/clearances")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

STICKERS_DIR    = Path("app/assets/stickers")
LOGOS_DIR       = Path("app/assets/logos")
FRONTEND_PUBLIC = Path("../frontend/public")

PRIMARY       = (0.078, 0.176, 0.431)
HEADER_COLOR  = (0.11,  0.22,  0.48)
TEXT_COLOR    = (0.05,  0.12,  0.30)

STICKER_MAP = {
    "Barangay":    "sticker-barangay.png",
    "City":        "sticker-city.png",
    "Accredited":  "sticker-accredited.png",
    "Hazardous":   "sticker-hazardous.png",
    "Exempted":    "sticker-exempted.png",
    "No Contract": None,
}


def find_asset(filename):
    for d in [LOGOS_DIR, STICKERS_DIR, FRONTEND_PUBLIC, Path("app/assets"), Path("public")]:
        p = d / filename
        if p.exists():
            return str(p)
    return None


def get_sticker_year():
    """Determine sticker year based on cutoff (November)."""
    now = datetime.now()
    if now.month >= 11:
        return now.year + 1
    return now.year


def get_sticker_path(hauler_type, year=None):
    if year is None:
        year = get_sticker_year()

    filename = STICKER_MAP.get(hauler_type)
    if not filename:
        return None

    base_name = filename.replace(".png", "")
    year_filename = f"{base_name}_{year}.png"

    for d in [STICKERS_DIR, FRONTEND_PUBLIC, Path("public")]:
        p = d / year_filename
        if p.exists():
            return str(p)
        p2 = d / filename
        if p2.exists():
            return str(p2)

    return None


def save_base64_image_to_temp(base64_string):
    """Save a base64 image to a temporary file and return the path."""
    if not base64_string:
        return None

    try:
        if ',' in base64_string:
            base64_string = base64_string.split(',')[1]

        image_data = base64.b64decode(base64_string)

        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
            tmp_file.write(image_data)
            return tmp_file.name
    except Exception as e:
        print(f"Error saving signature: {e}")
        return None


def wrap_text(c, text, font, size, max_width):
    words = text.split()
    lines, buf = [], ""
    for word in words:
        test = buf + (" " if buf else "") + word
        if c.stringWidth(test, font, size) <= max_width:
            buf = test
        else:
            if buf:
                lines.append(buf)
            buf = word
    if buf:
        lines.append(buf)
    return lines


def draw_spaced(c, text, x, y, font, size, target_width):
    if not text:
        return
    natural_w = c.stringWidth(text, font, size)
    n = len(text)
    if n <= 1 or natural_w >= target_width:
        c.setFont(font, size)
        c.drawString(x, y, text)
        return
    gap = (target_width - natural_w) / (n - 1)
    cx  = x
    c.setFont(font, size)
    for ch in text:
        c.drawString(cx, y, ch)
        cx += c.stringWidth(ch, font, size) + gap


def format_date(date_str: str) -> str:
    for fmt in ("%B %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%m/%d/%Y")
        except ValueError:
            continue
    return date_str


def draw_sticker_year(c, x, y, width, height, year):
    c.saveState()
    center_x = x + (width / 2) + 6.5 * mm
    center_y = y + (height / 2) - 3 * mm
    c.setFont("Helvetica-Bold", 25)
    c.setFillColorRGB(0.2, 0.2, 0.2)
    year_str = str(year)
    text_width = c.stringWidth(year_str, "Helvetica-Bold", 25)
    c.drawString(center_x - (text_width / 2), center_y - 10, year_str)
    c.restoreState()


def draw_signature(c, sig_base64, x, y, width=40*mm, height=15*mm):
    """Draw signature image from base64 string."""
    if not sig_base64:
        return False

    temp_path = save_base64_image_to_temp(sig_base64)
    if not temp_path or not os.path.exists(temp_path):
        return False

    try:
        c.drawImage(temp_path, x, y, width=width, height=height,
                    preserveAspectRatio=True, mask='auto')
        os.unlink(temp_path)
        return True
    except Exception as e:
        print(f"Error drawing signature: {e}")
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        return False


def generate_clearance_pdf(clearance_data: dict, filename: str) -> str:
    file_path = str(UPLOAD_DIR / filename)
    W, H = A4
    bc         = colors.Color(*PRIMARY)
    hc         = colors.Color(*HEADER_COLOR)
    text_color = colors.Color(*TEXT_COLOR)

    recommending_name  = clearance_data.get("recommending_name", "ANTONETTE NICOLE D. BAYOT")
    recommending_title = clearance_data.get("recommending_title", "ENGINEER I")
    recommending_sig   = clearance_data.get("recommending_signature")
    approving_name     = clearance_data.get("approving_name", "OSCAR B. LAURENCIANA")
    approving_title    = clearance_data.get("approving_title", "OIC-CENRO")
    approving_sig      = clearance_data.get("approving_signature")

    c = rl_canvas.Canvas(file_path, pagesize=A4)

    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, W, H, fill=1, stroke=0)

    b1 = 9   * mm
    b2 = 10.5* mm
    b3 = 12  * mm
    c.setStrokeColor(bc)
    c.setLineWidth(1.5)
    c.rect(b1, b1, W - 2*b1, H - 2*b1, fill=0, stroke=1)
    c.setLineWidth(1.5)
    c.rect(b2, b2, W - 2*b2, H - 2*b2, fill=0, stroke=1)
    c.setLineWidth(1.5)
    c.rect(b3, b3, W - 2*b3, H - 2*b3, fill=0, stroke=1)

    inner_m = b3 + 4*mm

    logo_size = 18*mm
    logo_gap  = 3*mm
    logos_w   = logo_size * 2 + logo_gap
    logos_x   = (W - logos_w) / 2
    logo_y    = H - inner_m - logo_size

    tagaytay_logo = find_asset("tagaytay-logo.png")
    if tagaytay_logo:
        c.drawImage(tagaytay_logo, logos_x, logo_y,
                    width=logo_size, height=logo_size,
                    preserveAspectRatio=True, anchor='c', mask='auto')

    bp_logo = find_asset("bp-logo.png")
    bp_x    = logos_x + logo_size + logo_gap
    if bp_logo:
        c.drawImage(bp_logo, bp_x, logo_y,
                    width=logo_size, height=logo_size,
                    preserveAspectRatio=True, anchor='c', mask='auto')

    t1_y = logo_y - 4.5*mm
    t2_y = t1_y   - 4.5*mm
    t3_y = t2_y   - 4.5*mm

    c.setFillColor(hc)
    c.setFont("Helvetica-Bold", 9.5)
    c.drawCentredString(W / 2, t1_y, "Republic of the Philippines")
    c.drawCentredString(W / 2, t2_y, "City Government of Tagaytay")
    c.setFont("Helvetica-Bold", 9.5)
    c.drawCentredString(W / 2, t3_y, "CITY ENVIRONMENT AND NATURAL RESOURCES OFFICE")

    blk_top = t1_y + 10*mm
    blk_bot = t3_y - 2*mm
    stk_h   = blk_top - blk_bot
    stk_w   = stk_h * 2.5
    stk_x   = inner_m
    stk_y   = blk_bot + 9*mm

    c.setStrokeColor(bc)
    c.setLineWidth(1.5)
    c.rect(21*mm, H - 40.65*mm, 42.5*mm, 21.4*mm, fill=0, stroke=1)

    current_year = get_sticker_year()
    sticker_path = get_sticker_path(clearance_data.get("hauler_type", ""), current_year)

    if sticker_path:
        c.drawImage(sticker_path, stk_x, stk_y,
                    width=stk_w, height=stk_h,
                    preserveAspectRatio=True, anchor='c', mask='auto')
        draw_sticker_year(c, stk_x, stk_y, stk_w, stk_h, current_year)

    sep_y = t3_y - 3*mm
    c.setStrokeColor(bc)
    c.setLineWidth(1.5)
    c.line(inner_m, sep_y, W - inner_m, sep_y)

    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 15)
    title_y = sep_y - 6.5*mm
    c.drawCentredString(W / 2, title_y, "ENVIRONMENTAL MANAGEMENT CLEARANCE")

    field_x     = inner_m + 2*mm
    val_end_x   = W - inner_m - 2*mm
    row_h       = 7*mm
    first_row_y = title_y - 13*mm
    colon_gap   = 3*mm

    fields = [
        ("Name of Establishment:",               clearance_data.get("establishment_name", "")),
        ("Business Identification Number (BIN):", clearance_data.get("bin_number", "N/A")),
        ("Line of Business:",                     clearance_data.get("business_line", "")),
        ("Name of Registered Owner:",             clearance_data.get("owner_name", "")),
        ("Location of Establishment:",            clearance_data.get("location", "")),
    ]

    y_cursor = first_row_y
    for label, value in fields:
        val_str   = str(value).upper() if value else ""
        lbl_val_x = field_x + c.stringWidth(label, "Helvetica-Bold", 10) + colon_gap
        lbl_max_w = val_end_x - lbl_val_x
        val_lines = wrap_text(c, val_str, "Helvetica-Bold", 10, lbl_max_w)

        c.setFillColor(text_color)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(field_x, y_cursor, label)

        first_natural = c.stringWidth(val_lines[0], "Helvetica-Bold", 10)
        n_first       = len(val_lines[0])
        raw_gap       = (lbl_max_w - first_natural) / (n_first - 1) if n_first > 1 and first_natural < lbl_max_w else 0
        char_gap      = min(raw_gap, 1.2)

        for j, line in enumerate(val_lines):
            line_y = y_cursor - j * row_h
            c.setFillColor(hc)
            c.setFont("Helvetica-Bold", 10)
            if char_gap > 0:
                cx = lbl_val_x
                for ch in line:
                    c.drawString(cx, line_y, ch)
                    cx += c.stringWidth(ch, "Helvetica-Bold", 10) + char_gap
            else:
                c.drawString(lbl_val_x, line_y, line)
            c.setStrokeColor(bc)
            c.setLineWidth(0.5)
            c.line(lbl_val_x, line_y - 1.2*mm, val_end_x, line_y - 1.2*mm)

        y_cursor -= row_h * len(val_lines)

    row6_y    = y_cursor
    issued_vx = field_x + c.stringWidth("Issued On:", "Helvetica-Bold", 10) + colon_gap
    valid_lx  = W / 2 + 5*mm
    valid_vx  = valid_lx + c.stringWidth("Valid Until:", "Helvetica-Bold", 10) + colon_gap

    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(field_x, row6_y, "Issued On:")
    c.setFillColor(hc)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(issued_vx, row6_y, format_date(clearance_data.get("issued_date", "")))
    c.setStrokeColor(bc)
    c.setLineWidth(0.5)
    c.line(issued_vx, row6_y - 1.2*mm, valid_lx - 5*mm, row6_y - 1.2*mm)

    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(valid_lx, row6_y, "Valid Until:")
    c.setFillColor(hc)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(valid_vx, row6_y, format_date(clearance_data.get("valid_until", "")))
    c.setStrokeColor(bc)
    c.line(valid_vx, row6_y - 1.2*mm, val_end_x, row6_y - 1.2*mm)

    row7_y  = y_cursor - row_h
    ctrl_vx = field_x + c.stringWidth("Control No.:", "Helvetica-Bold", 10) + colon_gap
    type_lx = W / 2 + 5*mm
    type_vx = type_lx + c.stringWidth("Type:", "Helvetica-Bold", 10) + colon_gap

    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(field_x, row7_y, "Control No.:")
    ctrl_str = clearance_data.get("control_number", "").upper()
    ctrl_nw  = c.stringWidth(ctrl_str, "Helvetica-Bold", 10)
    ctrl_aw  = type_lx - 5*mm - ctrl_vx
    ctrl_gap = min((ctrl_aw - ctrl_nw) / (len(ctrl_str) - 1), 1.2) if len(ctrl_str) > 1 and ctrl_nw < ctrl_aw else 0
    c.setFillColor(hc)
    c.setFont("Helvetica-Bold", 10)
    if ctrl_gap > 0:
        cx = ctrl_vx
        for ch in ctrl_str:
            c.drawString(cx, row7_y, ch)
            cx += c.stringWidth(ch, "Helvetica-Bold", 10) + ctrl_gap
    else:
        c.drawString(ctrl_vx, row7_y, ctrl_str)
    c.setStrokeColor(bc)
    c.setLineWidth(0.5)
    c.line(ctrl_vx, row7_y - 1.2*mm, type_lx - 5*mm, row7_y - 1.2*mm)

    c.setFillColor(text_color)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(type_lx, row7_y, "Type:")
    type_str = clearance_data.get("application_type", "NEW").upper()
    type_nw  = c.stringWidth(type_str, "Helvetica-Bold", 10)
    type_aw  = val_end_x - type_vx
    type_gap = min((type_aw - type_nw) / (len(type_str) - 1), 1.2) if len(type_str) > 1 and type_nw < type_aw else 0
    c.setFillColor(hc)
    c.setFont("Helvetica-Bold", 10)
    if type_gap > 0:
        cx = type_vx
        for ch in type_str:
            c.drawString(cx, row7_y, ch)
            cx += c.stringWidth(ch, "Helvetica-Bold", 10) + type_gap
    else:
        c.drawString(type_vx, row7_y, type_str)
    c.setStrokeColor(bc)
    c.line(type_vx, row7_y - 1.2*mm, val_end_x, row7_y - 1.2*mm)

    text_x = field_x
    text_w = val_end_x - text_x
    cond_y = first_row_y - 7 * row_h - 10*mm

    tx = text_x
    c.setFillColor(text_color)
    c.setFont("Helvetica", 13)
    c.drawString(tx, cond_y, "This ")
    tx += c.stringWidth("This ", "Helvetica", 13)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(tx, cond_y, "Clearance")
    tx += c.stringWidth("Clearance", "Helvetica-Bold", 13)
    c.setFont("Helvetica", 13)
    c.drawString(tx, cond_y, " is issued subject to the following conditions:")

    conditions = [
        "1. That operations of this establishment pose no immediate adverse environmental impact; or",
        "2. That the said operations of this establishment will comply with the rules and regulations imposed by our laws and ordinances;",
        "3. However, should the operations result to adverse environmental impact, any/all activities causing the same should be immediately stopped until such time that mitigating measures are affected;",
        "4. That the registered owner/s of this establishment warrant/s that no misrepresentation and/or withholding of material fact/s had been made herein that would affect the grant or denial of the clearance;",
        "5. That pertinent environmental permits and clearances must be secured and submitted first prior to operation;",
        "6. That waste should be properly managed/disposed as provided in the R.A. 9003, R.A. 8749, R.A. 9275, R.A. 6969 and other existing Environmental Laws and Ordinances;",
        "7. That the registered owner/s of this establishment is/are duty-bound to allow entry of our bonafide inspectors for the purpose of conducting inspections;",
        "8. That the registered owner/s of this establishment shall notify this Department if there is any alteration, modification and/or expansion in the firm\u2019s operation.",
    ]

    font_c = "Helvetica"
    size_c = 10
    lsp    = 4.7*mm
    ind    = 6*mm
    cond_y -= 7*mm

    c.setFont(font_c, size_c)
    c.setFillColor(text_color)

    for cond in conditions:
        first = True
        words = cond.split()
        buf, lines = "", []
        for word in words:
            test  = buf + (" " if buf else "") + word
            avail = text_w if first else (text_w - ind)
            if c.stringWidth(test, font_c, size_c) <= avail:
                buf = test
            else:
                lines.append((buf, first))
                first, buf = False, word
        lines.append((buf, first))

        for idx, (txt, is_first) in enumerate(lines):
            lx      = text_x if is_first else text_x + ind
            avail_w = text_w if is_first else (text_w - ind)
            is_last = (idx == len(lines) - 1)
            c.setFillColor(text_color)
            if is_last:
                c.setFont(font_c, size_c)
                c.drawString(lx, cond_y, txt)
            else:
                draw_spaced(c, txt, lx, cond_y, font_c, size_c, avail_w)
            cond_y -= lsp
        cond_y -= 1*mm

    cond_y -= 2*mm
    notice     = "Non-compliance and/or violation of any of the above conditions automatically revokes this clearance."
    nlines     = wrap_text(c, notice, "Helvetica-Bold", 13, text_w)
    first_nw   = c.stringWidth(nlines[0], "Helvetica-Bold", 13)
    n_first    = len(nlines[0])
    notice_gap = (text_w - first_nw) / (n_first - 1) if n_first > 1 and first_nw < text_w else 0
    c.setFillColor(colors.HexColor('#8B0000'))
    c.setFont("Helvetica-Bold", 13)
    for nl in nlines:
        if notice_gap > 0:
            cx = text_x
            for ch in nl:
                c.drawString(cx, cond_y, ch)
                cx += c.stringWidth(ch, "Helvetica-Bold", 13) + notice_gap
        else:
            c.drawString(text_x, cond_y, nl)
        cond_y -= 5.5*mm
    
    # Note
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.HexColor('#444444'))
    c.drawCentredString(W / 2, cond_y, "Note: Please always display this clearance in a visible area at all times.")
    cond_y -= 6*mm
    
    # Signatory section 
    cond_y -= 5*mm
    c.setFont("Helvetica", 9.5)
    c.setFillColor(text_color)
    c.drawString(W * 0.171, cond_y, "Recommending Approval:")
    c.drawString(W * 0.616, cond_y, "Approval:")

    left_cx  = W * 0.30
    right_cx = W * 0.72
    padding  = 3 * mm

    sig_width  = 35 * mm
    sig_height = 12 * mm

    name_y = cond_y - 15 * mm
    sig_y   = name_y

    if recommending_sig:
        draw_signature(
            c, recommending_sig,
            left_cx - sig_width / 2, sig_y,
            sig_width, sig_height
        )
    if approving_sig:
        draw_signature(
            c, approving_sig,
            right_cx - sig_width / 2, sig_y,
            sig_width, sig_height
        )

    left_name_w  = c.stringWidth(recommending_name,  "Helvetica-Bold", 10)
    right_name_w = c.stringWidth(approving_name, "Helvetica-Bold", 10)
    left_half    = left_name_w  / 2.25 + padding
    right_half   = right_name_w / 2.25 + padding

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(text_color)
    c.drawCentredString(left_cx,  name_y, recommending_name)
    c.drawCentredString(right_cx, name_y, approving_name)

    sig_line_y = name_y - 1*mm
    c.setStrokeColor(text_color)
    c.setLineWidth(0.7)
    c.line(left_cx  - left_half,  sig_line_y, left_cx  + left_half,  sig_line_y)
    c.line(right_cx - right_half, sig_line_y, right_cx + right_half, sig_line_y)

    c.setFont("Helvetica", 9)
    c.setFillColor(text_color)
    c.drawCentredString(left_cx,  sig_line_y - 3.5*mm, recommending_title)
    c.drawCentredString(right_cx, sig_line_y - 3.5*mm, approving_title)

    truck_h    = 18*mm
    truck_w    = truck_h * (666 / 374)
    truck_path = find_asset("truck-icon.png")
    truck_y    = sig_line_y - 3.5*mm - 27*mm
    if truck_path:
        c.drawImage(truck_path, (W - truck_w) / 2, truck_y,
                    width=truck_w, height=truck_h,
                    preserveAspectRatio=True, anchor='c', mask='auto')

    tag_font = "Helvetica-Oblique"
    tag_size = 10
    tag_y    = truck_y - 2*mm

    segments = [
        ("Better,",    (0.078, 0.176, 0.431)),
        (" cleaner, ",  (0.906, 0.329, 0.502)),
        ("& greener ", (0.102, 0.478, 0.102)),
        ("Tagaytay!",  (0.078, 0.176, 0.431)),
    ]

    total_w = sum(c.stringWidth(t, tag_font, tag_size) for t, _ in segments)
    tx = (W - total_w) / 2
    for txt, rgb in segments:
        c.setFillColorRGB(*rgb)
        c.setFont(tag_font, tag_size)
        c.drawString(tx, tag_y, txt)
        tx += c.stringWidth(txt, tag_font, tag_size)

    c.save()
    return str(file_path)
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, 
    Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from datetime import datetime
from pathlib import Path

# Directory for generated clearances
UPLOAD_DIR = Path("uploads/clearances")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

def get_background_color(color_name: str):
    """Convert color name to RGB values for background)"""
    colors_map = {
        "Blue": (0.95, 0.97, 1.0),    
        "Yellow": (1.0, 0.98, 0.9),   
        "Purple": (0.98, 0.95, 1.0),  
        "Red": (1.0, 0.95, 0.95),     
        "Green": (0.95, 1.0, 0.95),   
        "Gray": (0.98, 0.98, 0.98)    
    }
    return colors_map.get(color_name, (1, 1, 1))

def get_border_color(color_name: str):
    """Convert color name to RGB values for border"""
    colors_map = {
        "Blue": (0.0, 0.2, 0.6),       
        "Yellow": (0.8, 0.6, 0.0),     
        "Purple": (0.5, 0.1, 0.6),     
        "Red": (0.7, 0.1, 0.1),        
        "Green": (0.1, 0.5, 0.2),      
        "Gray": (0.4, 0.4, 0.4)        
    }
    return colors_map.get(color_name, (0.0, 0.2, 0.6))

def get_color_hex(color_rgb):
    """basta conversion daw tuple to rgb"""
    return f"#{int(color_rgb[0]*255):02x}{int(color_rgb[1]*255):02x}{int(color_rgb[2]*255):02x}"

def generate_clearance_pdf(clearance_data: dict, filename: str) -> str:
    """Generate Environmental Management Clearance"""
    file_path = UPLOAD_DIR / filename
    
    # a4 (210mm x 297mm)
    doc = SimpleDocTemplate(
        str(file_path),
        pagesize=A4,
        rightMargin=20*mm,
        leftMargin=20*mm,
        topMargin=15*mm,
        bottomMargin=15*mm
    )
    
    styles = getSampleStyleSheet()
    
    styles.add(ParagraphStyle(
        name='CenterSmall',
        parent=styles['Normal'],
        alignment=1, 
        fontSize=10,
        spaceAfter=2
    ))
    
    styles.add(ParagraphStyle(
        name='CenterMedium',
        parent=styles['Normal'],
        alignment=1,
        fontSize=12,
        spaceAfter=4,
        fontName='Helvetica-Bold'
    ))
    
    styles.add(ParagraphStyle(
        name='CenterLarge',
        parent=styles['Normal'],
        alignment=1,
        fontSize=16,
        spaceAfter=6,
        fontName='Helvetica-Bold'
    ))
    
    styles.add(ParagraphStyle(
        name='CenterTitle',
        parent=styles['Normal'],
        alignment=1,
        fontSize=18,
        spaceAfter=8,
        fontName='Helvetica-Bold',
        leading=22
    ))
    
    styles.add(ParagraphStyle(
        name='LeftBold',
        parent=styles['Normal'],
        alignment=0,
        fontSize=11,
        fontName='Helvetica-Bold',
        spaceAfter=4
    ))
    
    story = []
    
    color_name = clearance_data.get('clearance_color', 'Blue')
    bg_rgb = get_background_color(color_name)
    border_rgb = get_border_color(color_name)
    border_hex = get_color_hex(border_rgb)
    border_color = colors.Color(*border_rgb)
    
    # bg color
    def set_background(canvas, doc):
        canvas.saveState()
        canvas.setFillColorRGB(bg_rgb[0], bg_rgb[1], bg_rgb[2])
        canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.restoreState()
    
    # top border
    top_border_data = [[" "]]
    top_border = Table(top_border_data, colWidths=[170*mm], rowHeights=[3*mm])
    top_border.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), border_color),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(top_border)
    story.append(Spacer(1, 5*mm))
    
    # header
    story.append(Paragraph(
        f"""<font color="{border_hex}"><b>REPUBLIC OF THE PHILIPPINES</b></font>""",
        styles['CenterMedium']
    ))
    
    story.append(Paragraph(
        f"""<font color="{border_hex}"><b>CITY GOVERNMENT OF TAGAYTAY</b></font>""",
        styles['CenterMedium']
    ))
    
    story.append(Paragraph(
        f"""<font color="{border_hex}">City Environment and Natural Resources Office</font>""",
        styles['CenterSmall']
    ))
    
    story.append(Spacer(1, 8*mm))
    
    story.append(Paragraph(
        f"""<font color="{border_hex}" size="16"><b>ENVIRONMENTAL MANAGEMENT CLEARANCE</b></font>""",
        styles['CenterTitle']
    ))
    story.append(Spacer(1, 8*mm))
    
    story.append(Paragraph(
        f"""<font size="10"><b>Control No.:</b> <font color="{border_hex}"><b>{clearance_data.get('control_number', 'N/A')}</b></font></font>""",
        styles['Normal']
    ))
    story.append(Spacer(1, 6*mm))
    
    # business detaild
    details = [
        ["Name of Establishment:", clearance_data.get('establishment_name', '')],
        ["Business Identification Number (BIN):", clearance_data.get('bin_number', 'N/A')],
        ["Line of Business:", clearance_data.get('business_line', '')],
        ["Name of Registered Owner:", clearance_data.get('owner_name', '')],
        ["Location of Establishment:", clearance_data.get('location', '')],
        ["Issued On:", clearance_data.get('issued_date', '')],
        ["Valid Until:", clearance_data.get('valid_until', '')],
        ["Type:", clearance_data.get('application_type', 'NEW')],
    ]
    
    details_table = Table(details, colWidths=[70*mm, 100*mm])
    details_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('ALIGN', (0,0), (0,-1), 'LEFT'), 
        ('ALIGN', (1,0), (1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('TOPPADDING', (0,0), (-1,-1), 2),
        ('FONT', (0,0), (0,-1), 'Helvetica-Bold'),
    ]))
    story.append(details_table)
    story.append(Spacer(1, 8*mm))
    
    # conditions section
    story.append(Paragraph(
        "<b>This Clearance is issued subject to the following conditions:</b>",
        styles['LeftBold']
    ))
    story.append(Spacer(1, 2*mm))
    
    conditions = [
        "1. That operations of this establishment pose no immediate adverse environmental impact; or",
        "2. That the said operations of this establishment will comply with the rules and regulations imposed by our laws and ordinances;",
        "3. However, should the operations result in adverse environmental impact, any/all activities causing the same should be immediately stopped until such time that mitigating measures are affected;",
        "4. That the registered owner/s of this establishment warrant/s that no misrepresentation and/or withholding of material fact/s had been made herein that would affect the grant or denial of the clearance;",
        "5. That pertinent environmental permits and clearances must be secured and submitted first prior to operation;",
        "6. That waste should be properly managed/disposed as provided in the R.A. 9003, R.A. 8749, R.A. 9275, R.A. 6969 and other existing Environmental Laws and Ordinances;",
        "7. That the registered owner/s of this establishment shall notify this Department if there is any alteration, modification and/or expansion in the firm's operation."
    ]
    
    for condition in conditions:
        p = Paragraph(condition, styles['Normal'])
        story.append(p)
        story.append(Spacer(1, 1*mm))
    
    story.append(Spacer(1, 6*mm))
    
    # note
    story.append(Paragraph(
        """<font color="black"><b>Non-compliance and/or violation of any of the above conditions automatically revokes this clearance.</b></font>""",
        styles['Normal']
    ))
    story.append(Spacer(1, 10*mm))

    # signatories
    signatory_data = [
        ["Recommendation Approval:", "Approval:"],
        ["ANTONETTE NICOLE D. BAYOT", "OSCAR B. LAURENCIANA"],
        ["ENGINEER I", "OIC-CENRO"]
    ]

    signatory_table = Table(signatory_data, colWidths=[85*mm, 85*mm])
    signatory_table.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,-1), 'Helvetica'),
        ('FONTSIZE', (0,0), (-1,-1), 10),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (1,0), (1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('TOPPADDING', (0,0), (-1,-1), 4),
        ('BOTTOMPADDING', (0,0), (-1,-1), 4),
        ('FONT', (0,0), (0,1), 'Helvetica-Bold'),
        ('FONT', (1,0), (1,1), 'Helvetica-Bold'),
    ]))
    story.append(signatory_table)

    story.append(Spacer(1, 5*mm))

    # tagline?
    story.append(Paragraph(
        """<i>Better, cleaner & greener Tagaytay!</i>""",
        styles['CenterSmall']
    ))

    story.append(Spacer(1, 8*mm))

    # bottom border
    bottom_border_data = [[" "]]
    bottom_border = Table(bottom_border_data, colWidths=[170*mm], rowHeights=[2*mm])
    bottom_border.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), border_color),
        ('TOPPADDING', (0,0), (-1,-1), 0),
        ('BOTTOMPADDING', (0,0), (-1,-1), 0),
    ]))
    story.append(bottom_border)
    story.append(Spacer(1, 3*mm))
    
    # geneate pdf
    doc.build(story, onFirstPage=set_background, onLaterPages=set_background)
    return str(file_path)
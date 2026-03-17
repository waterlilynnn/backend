from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
import pandas as pd
import io
from datetime import datetime
from typing import List, Dict, Any

from app.core.database import get_db
from app.core.security import staff_only, log_audit
from app.models.user import User
from app.models.business_record import BusinessRecord, HaulerType, ApplicationType

router = APIRouter(
    prefix="/bulk",
    tags=["Bulk Import"]
)

def generate_control_number(db: Session, application_type: str, existing_business=None) -> str:
    """Generate control number based on application type"""
    
    year = datetime.now().year
    month = datetime.now().strftime("%m")
    
    # For RENEWAL, check if there's an existing control number
    if application_type == "RENEWAL" and existing_business and existing_business.control_number:
        return existing_business.control_number
    
    # For NEW or renewal without existing control number, generate new one
    latest = db.query(BusinessRecord).filter(
        BusinessRecord.control_number.like(f"EMC-{year}-{month}%")
    ).order_by(BusinessRecord.control_number.desc()).first()
    
    if latest and latest.control_number:
        last_seq = int(latest.control_number[-4:])
        new_seq = last_seq + 1
    else:
        new_seq = 1
    
    return f"EMC-{year}-{month}-{new_seq:04d}"

def parse_hauler_type(hauler_str: str) -> HaulerType:
    """Convert hauler string to enum"""
    mapping = {
        'BARANGAY': HaulerType.BARANGAY,
        'CITY': HaulerType.CITY,
        'ACCREDITED': HaulerType.ACCREDITED,
        'HAZARDOUS': HaulerType.HAZARDOUS,
        'EXEMPTED': HaulerType.EXEMPTED,
        'NO CONTRACT': HaulerType.NO_CONTRACT,
        'NO_CONTRACT': HaulerType.NO_CONTRACT,
    }
    cleaned = str(hauler_str).strip().upper()
    return mapping.get(cleaned, HaulerType.BARANGAY)

def parse_date(date_val):
    """Parse date safely"""
    if pd.isna(date_val) or not date_val:
        return None
    try:
        if isinstance(date_val, str):
            if date_val.isdigit():
                try:
                    from datetime import datetime, timedelta
                    excel_epoch = datetime(1899, 12, 30)
                    days = int(date_val)
                    return (excel_epoch + timedelta(days=days)).date()
                except:
                    pass
            
            for fmt in ['%m/%d/%Y', '%Y-%m-%d', '%d-%m-%Y', '%m-%d-%Y']:
                try:
                    return datetime.strptime(date_val, fmt).date()
                except:
                    continue
        
        return pd.to_datetime(date_val).date()
    except:
        return None

def parse_owner_name(owner_str):
    """Parse owner name into components"""
    if pd.isna(owner_str) or not owner_str:
        return None, None, None, None
    
    owner_raw = str(owner_str).strip().upper()
    
    last_name = ''
    first_name = ''
    middle_name = None
    suffix = None
    
    if ',' in owner_raw:
        parts = owner_raw.split(',', 1)
        last_name = parts[0].strip()
        
        first_part = parts[1].strip() if len(parts) > 1 else ""
        
        suffixes = ['JR', 'JR.', 'SR', 'SR.', 'III', 'IV', 'V']
        first_words = first_part.split()
        
        if first_words:
            first_name = first_words[0]
            
            if len(first_words) > 1 and first_words[-1] in suffixes:
                suffix = first_words[-1]
                middle_name = ' '.join(first_words[1:-1]) if len(first_words) > 2 else None
            elif len(first_words) > 1:
                middle_name = ' '.join(first_words[1:])
    else:
        last_name = owner_raw
    
    return last_name, first_name, middle_name, suffix

@router.post("/upload")
async def bulk_upload(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(staff_only)
):
    """Upload Excel/CSV file with business records"""
    
    if not (file.filename.endswith('.xlsx') or 
            file.filename.endswith('.xls') or 
            file.filename.endswith('.csv')):
        raise HTTPException(400, "File must be Excel or CSV")
    
    try:
        contents = await file.read()
        
        if file.filename.endswith('.csv'):
            encodings_to_try = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
            df = None
            last_error = None
            
            for encoding in encodings_to_try:
                try:
                    df = pd.read_csv(io.BytesIO(contents), encoding=encoding)
                    print(f"Successfully read CSV with {encoding} encoding")
                    break
                except UnicodeDecodeError as e:
                    last_error = e
                    continue
            
            if df is None:
                raise HTTPException(400, f"Could not read CSV file. Last error: {last_error}")
        else:
            df = pd.read_excel(io.BytesIO(contents))
        
        stats = {
            'total': len(df),
            'success': 0,
            'failed': 0,
            'errors': [],
            'new': 0,
            'renewals': 0
        }
        
        for index, row in df.iterrows():
            try:
                # Application Date
                application_date = None
                if pd.notna(row.get('Column 1')):
                    application_date = parse_date(row['Column 1'])
                    if not application_date:
                        application_date = str(row['Column 1'])
                
                # BIN Number
                bin_number = None
                if pd.notna(row.get('BIN')):
                    bin_number = str(row['BIN']).strip()
                
                # Establishment Name
                establishment_name = ''
                if pd.notna(row.get('NAME OF ESTABLISHMENT')):
                    establishment_name = str(row['NAME OF ESTABLISHMENT']).strip()
                
                # Business Line
                business_line = ''
                if pd.notna(row.get('BUSINESS LINE')):
                    business_line = str(row['BUSINESS LINE']).strip()
                
                # Business Owner
                owner_name_raw = None
                last_name = ''
                first_name = ''
                middle_name = None
                suffix = None
                
                if pd.notna(row.get('BUSINESS OWNER')):
                    owner_name_raw = str(row['BUSINESS OWNER']).strip()
                    last_name, first_name, middle_name, suffix = parse_owner_name(owner_name_raw)
                
                # Location
                location = None
                if pd.notna(row.get('LOCATION')):
                    location = str(row['LOCATION']).strip().upper()
                
                # Application Type
                type_raw = ''
                if pd.notna(row.get('TYPE')):
                    type_raw = str(row['TYPE']).strip().upper()
                
                app_type = ApplicationType.RENEWAL if 'RENEWAL' in type_raw else ApplicationType.NEW
                
                if app_type == ApplicationType.RENEWAL:
                    stats['renewals'] += 1
                else:
                    stats['new'] += 1
                
                # Hauler Type
                hauler_raw = 'BARANGAY'
                if pd.notna(row.get('HAULER')):
                    hauler_raw = str(row['HAULER']).strip()
                
                hauler_type = parse_hauler_type(hauler_raw)
                
                # Dates
                date_issued = None
                if pd.notna(row.get('DATE ISSUED')):
                    date_issued = parse_date(row['DATE ISSUED'])
                
                validity = None
                if pd.notna(row.get('VALIDITY')):
                    validity = parse_date(row['VALIDITY'])
                
                # Check if existing (for renewal)
                existing = None
                if bin_number:
                    existing = db.query(BusinessRecord).filter(
                        BusinessRecord.bin_number == bin_number
                    ).first()
                
                # Generate control number if not provided
                control_number = None
                if pd.notna(row.get('EMC-ID')):
                    control_number = str(row['EMC-ID']).strip()
                else:
                    control_number = generate_control_number(db, app_type, existing)
                
                # Sticker Color
                color_map = {
                    HaulerType.BARANGAY: "Grayish Blue",
                    HaulerType.CITY: "Yellow",
                    HaulerType.ACCREDITED: "Violet",
                    HaulerType.HAZARDOUS: "To be determined",
                    HaulerType.EXEMPTED: "To be determined",
                    HaulerType.NO_CONTRACT: "To be determined"
                }
                sticker_color = color_map.get(hauler_type, "White")
                
                business = BusinessRecord(
                    application_date=application_date,
                    bin_number=bin_number,
                    establishment_name=establishment_name,
                    business_line=business_line,
                    owner_name_raw=owner_name_raw,
                    owner_last_name=last_name,
                    owner_first_name=first_name,
                    owner_middle_name=middle_name,
                    owner_suffix=suffix,
                    location=location,
                    hauler_type=hauler_type,
                    application_type=app_type,
                    status="Approved",
                    control_number=control_number,
                    date_issued=date_issued or datetime.now().date(),
                    validity=validity or datetime(datetime.now().year, 12, 31).date(),
                    sticker_color=sticker_color,
                    created_by=current_user.id,
                    previous_record_id=existing.id if existing and app_type == "RENEWAL" else None
                )
                
                db.add(business)
                db.flush()
                stats['success'] += 1
                
            except Exception as e:
                print(f"❌ Error on row {index + 2}: {str(e)}")
                stats['failed'] += 1
                stats['errors'].append({
                    'row': index + 2,
                    'error': str(e),
                    'data': row.to_dict() if hasattr(row, 'to_dict') else str(row)
                })
        
        db.commit()
        
        log_audit(
            db, 
            current_user.id, 
            "BULK_IMPORT", 
            "BUSINESS", 
            None, 
            {
                "total": stats['total'],
                "success": stats['success'],
                "failed": stats['failed']
            }
        )
        
        return {
            "success": True,
            "message": f"Successfully imported {stats['success']} out of {stats['total']} records",
            "stats": stats
        }
        
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
        raise HTTPException(500, f"Upload failed: {str(e)}")
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.business_record import BusinessRecord, ApplicationType
from datetime import datetime
import re

def fix_existing_data():
    """Fix application_type, application_date, and owner names for existing records"""
    
    db = SessionLocal()
    
    try:
        print("=" * 60)
        print("FIXING EXISTING BUSINESS RECORDS")
        print("=" * 60)
        
        # Kunin lahat ng records
        records = db.query(BusinessRecord).all()
        print(f"\nTotal records to check: {len(records)}")
        
        updated_types = 0
        updated_dates = 0
        updated_owners = 0
        
        for record in records:
            changes = []
            
            # ===== FIX 1: Application Type =====
            # Check kung dapat RENEWAL based sa previous_record_id or control_number pattern
            if not record.application_type or record.application_type == ApplicationType.NEW:
                # Check if may previous_record_id
                if record.previous_record_id:
                    record.application_type = ApplicationType.RENEWAL
                    updated_types += 1
                    changes.append("type→RENEWAL (has previous)")
                
                # Check if control number indicates renewal (may existing number)
                elif record.control_number and record.id > 1000:  # Assumption: mas bago ang renewals
                    # Optional: check kung may existing business na same name
                    existing = db.query(BusinessRecord).filter(
                        BusinessRecord.establishment_name == record.establishment_name,
                        BusinessRecord.id < record.id
                    ).first()
                    if existing:
                        record.application_type = ApplicationType.RENEWAL
                        updated_types += 1
                        changes.append("type→RENEWAL (by name)")
            
            # ===== FIX 2: Application Date =====
            # Kung walang application_date, gamitin ang created_at
            if not record.application_date:
                record.application_date = record.created_at
                updated_dates += 1
                changes.append("date set")
            
            # ===== FIX 3: Owner Names =====
            # Kung may owner_name_raw pero walang split names
            if record.owner_name_raw and (not record.owner_last_name or not record.owner_first_name):
                # Try to parse "LAST, FIRST MIDDLE" format
                owner_raw = record.owner_name_raw.strip().upper()
                
                # Pattern: "LAST, FIRST MIDDLE" or "LAST, FIRST"
                if ',' in owner_raw:
                    parts = owner_raw.split(',', 1)
                    record.owner_last_name = parts[0].strip()
                    
                    first_part = parts[1].strip() if len(parts) > 1 else ""
                    
                    # Check for middle name
                    first_parts = first_part.split()
                    if len(first_parts) >= 2:
                        record.owner_first_name = first_parts[0]
                        record.owner_middle_name = ' '.join(first_parts[1:])
                    else:
                        record.owner_first_name = first_part
                    
                    updated_owners += 1
                    changes.append(f"owner parsed: {record.owner_last_name}, {record.owner_first_name}")
            
            if changes:
                print(f"\nRecord {record.id}: {record.establishment_name}")
                for change in changes:
                    print(f"     • {change}")
        
        # Commit changes
        db.commit()
        
        print("\n" + "=" * 60)
        print("FIX COMPLETED")
        print("=" * 60)
        print(f"\nSummary:")
        print(f"   • Updated Application Types: {updated_types}")
        print(f"   • Updated Application Dates: {updated_dates}")
        print(f"   • Updated Owner Names: {updated_owners}")
        
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    fix_existing_data()
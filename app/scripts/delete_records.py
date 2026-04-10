import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.models.business_record import BusinessRecord
from app.models.clearance import Clearance
from app.models.inspection import Inspection
from app.models.requirement import RequirementSubmission

def delete_business_records(ids_to_delete):
    db = SessionLocal()
    try:
        # Check which records exist
        records = db.query(BusinessRecord).filter(BusinessRecord.id.in_(ids_to_delete)).all()
        
        if not records:
            print(f"No records found with IDs: {ids_to_delete}")
            return
        
        print(f"Found {len(records)} records to delete:")
        for r in records:
            print(f"  - ID {r.id}: {r.establishment_name} (BIN: {r.bin_number})")
        
        confirm = input("\nAre you sure you want to delete these records? (yes/no): ")
        if confirm.lower() != 'yes':
            print("Deletion cancelled.")
            return
        
        # Delete from all related tables using raw SQL to ensure we catch everything
        print("\nDeleting related records...")
        
        # List of tables that might have foreign keys to tbl_business
        related_tables = [
            'tbl_clearances',
            'tbl_inspections', 
            'tbl_requirement_submissions',
            'tbl_requirements',  # This was missing!
        ]
        
        for table in related_tables:
            try:
                # Check if table exists
                result = db.execute(text(f"""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_schema = DATABASE() AND table_name = '{table}'
                """))
                if result.scalar() > 0:
                    # Check if business_record_id or business_id column exists
                    col_check = db.execute(text(f"""
                        SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_schema = DATABASE() 
                        AND table_name = '{table}'
                        AND column_name IN ('business_record_id', 'business_id')
                    """))
                    
                    if col_check.scalar() > 0:
                        # Determine which column to use
                        col_name = 'business_record_id'
                        if table == 'tbl_requirement_submissions':
                            col_name = 'business_id'
                        elif table == 'tbl_requirements':
                            col_name = 'business_record_id'
                        
                        # Delete records
                        placeholders = ','.join(['%s'] * len(ids_to_delete))
                        delete_sql = text(f"DELETE FROM {table} WHERE {col_name} IN ({placeholders})")
                        result = db.execute(delete_sql, ids_to_delete)
                        print(f"  ✓ Deleted {result.rowcount} records from {table}")
            except Exception as e:
                print(f"  ⚠ Could not delete from {table}: {e}")
        
        # Now delete the business records
        print("\nDeleting business records...")
        deleted_count = db.query(BusinessRecord).filter(BusinessRecord.id.in_(ids_to_delete)).delete(synchronize_session=False)
        
        db.commit()
        print(f"\n✓ Successfully deleted {deleted_count} business records")
        
    except Exception as e:
        db.rollback()
        print(f"\n✗ Error: {e}")
        print("\nIf the error persists, try running this SQL directly in phpMyAdmin:")
        print("\n-- First, delete from all related tables:")
        for table in ['tbl_requirements', 'tbl_clearances', 'tbl_inspections', 'tbl_requirement_submissions']:
            print(f"DELETE FROM {table} WHERE business_record_id IN ({','.join(map(str, ids_to_delete))});")
        print(f"\n-- Then delete the business records:")
        print(f"DELETE FROM tbl_business WHERE id IN ({','.join(map(str, ids_to_delete))});")
    finally:
        db.close()

if __name__ == "__main__":
    ids = [1607, 1609, 1610, 1611, 1612, 1613, 1614, 1615, 1616, 
           1594, 1595, 1596, 1599, 1600, 1601, 1602, 1603, 1604, 1605, 1606]
    delete_business_records(ids)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

def run():
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Add hauler_type column if it doesn't exist
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_name = 'tbl_requirement_templates'
                AND column_name = 'hauler_type'
            """))
            
            if result.scalar() == 0:
                conn.execute(text("""
                    ALTER TABLE tbl_requirement_templates
                    ADD COLUMN hauler_type VARCHAR(50) NULL DEFAULT NULL
                """))
                print("✓ Added hauler_type column to tbl_requirement_templates")
            else:
                print("  hauler_type column already exists — skipped")
            
            trans.commit()
            print("✓ Migration complete")
        except Exception as e:
            trans.rollback()
            print(f"✗ Migration failed: {e}")
            raise

if __name__ == "__main__":
    run()
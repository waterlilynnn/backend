"""
Migration: Add archive fields to tbl_clearances
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from app.core.database import engine

def run():
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            # Check and add is_archived
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'tbl_clearances'
                  AND column_name = 'is_archived'
            """))
            if result.scalar() == 0:
                conn.execute(text("ALTER TABLE tbl_clearances ADD COLUMN is_archived BOOLEAN DEFAULT FALSE"))
                print("✓ Added is_archived column")
            else:
                print("  is_archived already exists")

            # Check and add archived_at
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'tbl_clearances'
                  AND column_name = 'archived_at'
            """))
            if result.scalar() == 0:
                conn.execute(text("ALTER TABLE tbl_clearances ADD COLUMN archived_at DATETIME NULL"))
                print("✓ Added archived_at column")

            # Check and add archived_by
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'tbl_clearances'
                  AND column_name = 'archived_by'
            """))
            if result.scalar() == 0:
                conn.execute(text("""
                    ALTER TABLE tbl_clearances 
                    ADD COLUMN archived_by INT NULL,
                    ADD FOREIGN KEY (archived_by) REFERENCES tbl_users(id)
                """))
                print("✓ Added archived_by column")

            # Check and add unarchived_at
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'tbl_clearances'
                  AND column_name = 'unarchived_at'
            """))
            if result.scalar() == 0:
                conn.execute(text("ALTER TABLE tbl_clearances ADD COLUMN unarchived_at DATETIME NULL"))
                print("✓ Added unarchived_at column")

            # Check and add unarchived_by
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = DATABASE()
                  AND table_name = 'tbl_clearances'
                  AND column_name = 'unarchived_by'
            """))
            if result.scalar() == 0:
                conn.execute(text("""
                    ALTER TABLE tbl_clearances 
                    ADD COLUMN unarchived_by INT NULL,
                    ADD FOREIGN KEY (unarchived_by) REFERENCES tbl_users(id)
                """))
                print("✓ Added unarchived_by column")

            trans.commit()
            print("\n✓ Migration complete!")
            
        except Exception as e:
            trans.rollback()
            print(f"✗ Migration failed: {e}")
            raise

if __name__ == "__main__":
    run()
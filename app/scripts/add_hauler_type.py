import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from app.core.database import engine

def run():
    with engine.connect() as conn:
        trans = conn.begin()
        try:
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
                print("✓ Added hauler_type column")
            
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_name = 'tbl_requirement_submissions'
            """))
            
            if result.scalar() == 0:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tbl_requirement_submissions (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        business_id INT NOT NULL,
                        template_id INT NOT NULL,
                        is_submitted BOOLEAN DEFAULT FALSE,
                        submitted_at DATETIME,
                        submitted_by INT,
                        notes TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (business_id) REFERENCES tbl_business(id) ON DELETE CASCADE,
                        FOREIGN KEY (template_id) REFERENCES tbl_requirement_templates(id) ON DELETE CASCADE,
                        FOREIGN KEY (submitted_by) REFERENCES tbl_users(id)
                    )
                """))
                print("✓ Created tbl_requirement_submissions")
            
            trans.commit()
            print("✓ Migration complete")
        except Exception as e:
            trans.rollback()
            print(f"✗ Migration failed: {e}")
            raise

if __name__ == "__main__":
    run()
import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = str(Path(__file__).parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from sqlalchemy import create_engine, text
from app.core.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

def seed_requirements():
    """Add requirement_checklist table to database"""
    
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    
    try:
        engine = create_engine(DATABASE_URL)
        
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            try:
                print("=" * 50)
                print("Adding requirements table...")
                print("=" * 50)
                
                # Check if table already exists
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = 'tbl_requirement_checklist'
                """))
                
                if result.scalar() == 0:
                    # Create the table
                    conn.execute(text("""
                        CREATE TABLE tbl_requirement_checklist (
                            id INT PRIMARY KEY AUTO_INCREMENT,
                            business_record_id INT NOT NULL UNIQUE,
                            
                            dti_registration BOOLEAN DEFAULT FALSE,
                            dti_registration_file VARCHAR(500),
                            
                            mayor_permit BOOLEAN DEFAULT FALSE,
                            mayor_permit_file VARCHAR(500),
                            
                            occupancy_permit BOOLEAN DEFAULT FALSE,
                            occupancy_permit_file VARCHAR(500),
                            
                            sanitation_permit BOOLEAN DEFAULT FALSE,
                            sanitation_permit_file VARCHAR(500),
                            
                            fire_safety_cert BOOLEAN DEFAULT FALSE,
                            fire_safety_cert_file VARCHAR(500),
                            
                            environmental_compliance BOOLEAN DEFAULT FALSE,
                            environmental_compliance_file VARCHAR(500),
                            
                            additional_documents JSON,
                            
                            submitted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                            submitted_by INT NOT NULL,
                            last_updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                            last_updated_by INT,
                            
                            FOREIGN KEY (business_record_id) REFERENCES tbl_business(id),
                            FOREIGN KEY (submitted_by) REFERENCES tbl_users(id),
                            FOREIGN KEY (last_updated_by) REFERENCES tbl_users(id)
                        )
                    """))
                    print("✓ Created tbl_requirement_checklist")
                else:
                    print("✓ Table already exists")
                
                trans.commit()
                print("=" * 50)
                print("Requirements table added successfully!")
                print("=" * 50)
                
            except Exception as e:
                trans.rollback()
                print(f"Error: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
                
    except Exception as e:
        print(f"Database connection error: {str(e)}")
        raise

if __name__ == "__main__":
    seed_requirements()
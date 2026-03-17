import sys
import os
from pathlib import Path

backend_dir = str(Path(__file__).parent.parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
    print(f"Added {backend_dir} to Python path")

try:
    from app.core.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
    print("Successfully imported config")
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Current sys.path: {sys.path}")
    sys.exit(1)

from sqlalchemy import create_engine, text
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_database():
    """Migrate existing database to new schema"""
    
    # Construct database URL
    DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    print(f"Connecting to database: {DB_HOST}:{DB_PORT}/{DB_NAME}")
    
    try:
        engine = create_engine(DATABASE_URL)
        
        with engine.connect() as conn:
            # Start transaction
            trans = conn.begin()
            try:
                logger.info("=" * 50)
                logger.info("STARTING DATABASE MIGRATION")
                logger.info("=" * 50)
                logger.info("\nStep 1: Updating tbl_users...")
                
                # Check if username column exists
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'tbl_users' AND column_name = 'username'
                """))
                
                if result.scalar() == 0:
                    conn.execute(text("""
                        ALTER TABLE tbl_users
                        ADD COLUMN username VARCHAR(50) UNIQUE,
                        ADD COLUMN last_login DATETIME,
                        ADD COLUMN login_attempts INT DEFAULT 0
                    """))
                    logger.info("Added username, last_login, login_attempts to tbl_users")
                    
                    conn.execute(text("""
                        UPDATE tbl_users SET username = SUBSTRING_INDEX(email, '@', 1)
                    """))
                    logger.info("Set usernames from email addresses")
                else:
                    logger.info("Username column already exists")
                
                logger.info("\nStep 2: Renaming tbl_applications to tbl_business...")
                
                # Check if new table already exists
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = 'tbl_business'
                """))
                
                if result.scalar() == 0:
                    # Check if old table exists
                    result2 = conn.execute(text("""
                        SELECT COUNT(*) FROM information_schema.tables 
                        WHERE table_name = 'tbl_applications'
                    """))
                    
                    if result2.scalar() > 0:
                        conn.execute(text("""
                            RENAME TABLE tbl_applications TO tbl_business
                        """))
                        logger.info("Renamed tbl_applications to tbl_business")
                    else:
                        logger.info("tbl_applications doesn't exist, creating new table...")
                        # Create the table if it doesn't exist 
                        conn.execute(text("""
                            CREATE TABLE IF NOT EXISTS tbl_business (
                                id INT PRIMARY KEY AUTO_INCREMENT,
                                establishment_name VARCHAR(200),
                                owner_last_name VARCHAR(100),
                                owner_first_name VARCHAR(100),
                                barangay VARCHAR(100),
                                hauler_type VARCHAR(50),
                                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                                created_by INT
                            )
                        """))
                else:
                    logger.info("tbl_business already exists")
                
                logger.info("\nStep 3: Adding new columns to tbl_business...")
                
                columns_to_add = [
                    ("owner_last_name", "VARCHAR(100)"),
                    ("owner_first_name", "VARCHAR(100)"),
                    ("owner_middle_name", "VARCHAR(100)"),
                    ("owner_suffix", "VARCHAR(50)"),
                    ("contact_number", "VARCHAR(20)"),
                    ("violation_date", "DATE"),
                    ("violation_details", "TEXT"),
                    ("violation_status", "VARCHAR(20) DEFAULT 'None'"),
                    ("revoked_reason", "TEXT"),
                    ("reissued_date", "DATE"),
                    ("approved_by", "INT"),
                    ("approved_at", "DATETIME"),
                    ("previous_record_id", "INT")
                ]
                
                for col_name, col_type in columns_to_add:
                    # Check if column exists
                    result = conn.execute(text(f"""
                        SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_name = 'tbl_business' AND column_name = '{col_name}'
                    """))
                    
                    if result.scalar() == 0:
                        try:
                            conn.execute(text(f"ALTER TABLE tbl_business ADD COLUMN {col_name} {col_type}"))
                            logger.info(f"Added {col_name} column")
                        except Exception as e:
                            logger.warning(f"Could not add {col_name}: {str(e)}")
                
                logger.info("\nStep 4: Parsing owner_name into components...")
                
                # Check if owner_name column exists
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.columns 
                    WHERE table_name = 'tbl_business' AND column_name = 'owner_name'
                """))
                
                if result.scalar() > 0:
                    conn.execute(text("""
                        UPDATE tbl_business
                        SET 
                            owner_last_name = TRIM(SUBSTRING_INDEX(owner_name, ',', 1)),
                            owner_first_name = TRIM(SUBSTRING_INDEX(owner_name, ',', -1))
                        WHERE owner_last_name IS NULL AND owner_name IS NOT NULL
                    """))
                    logger.info("Parsed owner_name into last/first name")
                
                logger.info("\nStep 5: Creating new tables...")
                
                # Create tbl_inspections
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tbl_inspections (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        business_record_id INT NOT NULL,
                        inspector_id INT NOT NULL,
                        inspection_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                        status ENUM('PASSED', 'WITH VIOLATION') NOT NULL,
                        remarks TEXT,
                        scanned_from_qr BOOLEAN DEFAULT FALSE,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (business_record_id) REFERENCES tbl_business(id),
                        FOREIGN KEY (inspector_id) REFERENCES tbl_users(id)
                    )
                """))
                logger.info("Created tbl_inspections")
                
                # Create tbl_audit
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tbl_audit (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        user_id INT NOT NULL,
                        action VARCHAR(50) NOT NULL,
                        entity_type VARCHAR(50) NOT NULL,
                        entity_id INT,
                        details JSON,
                        ip_address VARCHAR(45),
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES tbl_users(id)
                    )
                """))
                logger.info("Created tbl_audit")
                
                # Create tbl_print_logs
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS tbl_print_logs (
                        id INT PRIMARY KEY AUTO_INCREMENT,
                        clearance_id INT NOT NULL,
                        printed_by INT NOT NULL,
                        printed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        print_type ENUM('FIRST PRINT', 'REPRINT') DEFAULT 'FIRST PRINT',
                        reason VARCHAR(255),
                        FOREIGN KEY (clearance_id) REFERENCES tbl_clearances(id),
                        FOREIGN KEY (printed_by) REFERENCES tbl_users(id)
                    )
                """))
                logger.info("Created tbl_print_logs")
                
                logger.info("\nStep 6: Updating tbl_clearances...")
                
                # Check if tbl_clearances exists
                result = conn.execute(text("""
                    SELECT COUNT(*) FROM information_schema.tables 
                    WHERE table_name = 'tbl_clearances'
                """))
                
                if result.scalar() > 0:
                    result = conn.execute(text("""
                        SELECT COUNT(*) FROM information_schema.columns 
                        WHERE table_name = 'tbl_clearances' AND column_name = 'application_id'
                    """))
                    
                    if result.scalar() > 0:
                        # Check if business_record_id already exists
                        result2 = conn.execute(text("""
                            SELECT COUNT(*) FROM information_schema.columns 
                            WHERE table_name = 'tbl_clearances' AND column_name = 'business_record_id'
                        """))
                        
                        if result2.scalar() == 0:
                            try:
                                conn.execute(text("""
                                    ALTER TABLE tbl_clearances 
                                    CHANGE COLUMN application_id business_record_id INT NOT NULL
                                """))
                                logger.info("Renamed application_id to business_record_id")
                            except Exception as e:
                                logger.warning(f"Could not rename column: {str(e)}")
                    
                    # Add new columns to clearances
                    clearance_columns = [
                        ("print_count", "INT DEFAULT 1"),
                        ("last_printed_at", "DATETIME"),
                        ("last_printed_by", "INT"),
                        ("is_active", "BOOLEAN DEFAULT TRUE")
                    ]
                    
                    for col_name, col_type in clearance_columns:
                        result = conn.execute(text(f"""
                            SELECT COUNT(*) FROM information_schema.columns 
                            WHERE table_name = 'tbl_clearances' AND column_name = '{col_name}'
                        """))
                        
                        if result.scalar() == 0:
                            try:
                                conn.execute(text(f"ALTER TABLE tbl_clearances ADD COLUMN {col_name} {col_type}"))
                                logger.info(f"Added {col_name} to tbl_clearances")
                            except Exception as e:
                                logger.warning(f"Could not add {col_name}: {str(e)}")
                else:
                    logger.info("tbl_clearances doesn't exist yet")
                
                # Commit transaction
                trans.commit()
                
                logger.info("\n" + "=" * 50)
                logger.info("DATABASE MIGRATION COMPLETED SUCCESSFULLY!")
                logger.info("=" * 50)
                
                # Show summary
                logger.info("\nMigration Summary:")
                
                # Count records
                tables = ['tbl_users', 'tbl_business', 'tbl_clearances', 
                         'tbl_inspections', 'tbl_audit', 'tbl_print_logs']
                
                for table in tables:
                    try:
                        result = conn.execute(text(f"SELECT COUNT(*) FROM {table}"))
                        count = result.scalar()
                        logger.info(f"  • {table}: {count} records")
                    except:
                        logger.info(f"  • {table}: Table not found")
                
            except Exception as e:
                trans.rollback()
                logger.error(f"Migration failed: {str(e)}")
                import traceback
                traceback.print_exc()
                raise
                
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("DATABASE MIGRATION TOOL")
    print("=" * 50)
    print(f"Current directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    print("=" * 50 + "\n")
    
    migrate_database()
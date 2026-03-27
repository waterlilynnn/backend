import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from app.core.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

columns = [
    ("is_resolved",       "BOOLEAN DEFAULT FALSE"),
    ("resolved_at",       "DATETIME"),
    ("resolved_by",       "INT"),
    ("resolved_remarks",  "TEXT"),
]

with engine.connect() as conn:
    trans = conn.begin()
    try:
        for col_name, col_type in columns:
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = '{DB_NAME}'
                  AND table_name   = 'tbl_inspections'
                  AND column_name  = '{col_name}'
            """))
            if result.scalar() == 0:
                conn.execute(text(f"ALTER TABLE tbl_inspections ADD COLUMN {col_name} {col_type}"))
                print(f"  ✓ Added column: {col_name}")
            else:
                print(f"  – Already exists: {col_name}")
        trans.commit()
        print("\nMigration complete.")
    except Exception as e:
        trans.rollback()
        print(f"Migration failed: {e}")
        raise
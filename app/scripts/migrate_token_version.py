import sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from app.core.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

DATABASE_URL = f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(DATABASE_URL)

columns = [
    ("token_version", "INT DEFAULT 0"),
]

with engine.connect() as conn:
    trans = conn.begin()
    try:
        for col_name, col_type in columns:
            result = conn.execute(text(f"""
                SELECT COUNT(*) FROM information_schema.columns
                WHERE table_schema = '{DB_NAME}'
                  AND table_name   = 'tbl_users'
                  AND column_name  = '{col_name}'
            """))
            if result.scalar() == 0:
                conn.execute(text(f"ALTER TABLE tbl_users ADD COLUMN {col_name} {col_type}"))
                print(f"  + Added column: {col_name}")
            else:
                print(f"  - Already exists: {col_name}")

        # Backfill any NULLs (existing rows) to 0
        conn.execute(text("UPDATE tbl_users SET token_version = 0 WHERE token_version IS NULL"))

        trans.commit()
        print("\nMigration complete.")
    except Exception as e:
        trans.rollback()
        print(f"Migration failed: {e}")
        raise
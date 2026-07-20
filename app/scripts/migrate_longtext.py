import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.core.database import engine
from sqlalchemy import text

def run():
    with engine.connect() as conn:
        conn.execute(text(
            "ALTER TABLE tbl_settings MODIFY COLUMN `value` LONGTEXT NULL;"
        ))
        conn.commit()
    print("[Migration] tbl_settings.value → LONGTEXT  ✓")

if __name__ == "__main__":
    run()
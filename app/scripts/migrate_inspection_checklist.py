"""
Migration: create tbl_inspection_checklist

Run once:
    cd backend
    python -m app.scripts.migrate_inspection_checklist
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import text
from app.core.database import engine


def run():
    with engine.connect() as conn:
        trans = conn.begin()
        try:
            result = conn.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables
                WHERE table_schema = DATABASE()
                  AND table_name = 'tbl_inspection_checklist'
            """))
            if result.scalar() > 0:
                print("  tbl_inspection_checklist already exists — skipped")
                trans.commit()
                return

            conn.execute(text("""
                CREATE TABLE tbl_inspection_checklist (
                    id                  INT PRIMARY KEY AUTO_INCREMENT,
                    inspection_id       INT NOT NULL,

                    -- DENR/LLDA Permits (EXISTING / NO_EXISTING per permit)
                    emb_ecc             VARCHAR(20) DEFAULT NULL,
                    emb_cnc             VARCHAR(20) DEFAULT NULL,
                    pamb_clearance      VARCHAR(20) DEFAULT NULL,
                    discharge_permit    VARCHAR(20) DEFAULT NULL,

                    -- City Permits (TEMPORARY / PERMANENT per permit)
                    sanitary_permit     VARCHAR(20) DEFAULT NULL,
                    business_permit     VARCHAR(20) DEFAULT NULL,

                    -- Solid Waste Management Facility (JSON array of checked items)
                    swm_facilities      JSON DEFAULT NULL,

                    -- Solid Waste Hauling (JSON: {category: hauler_type})
                    sw_hauling          JSON DEFAULT NULL,

                    -- IEC Materials
                    has_iec_materials   TINYINT(1) DEFAULT NULL,

                    -- Proper Waste Segregation
                    proper_segregation  TINYINT(1) DEFAULT NULL,

                    -- Wastewater Treatment (JSON array of checked items)
                    wwt_facilities      JSON DEFAULT NULL,

                    -- Regular Desludging
                    desludging          VARCHAR(100) DEFAULT NULL,
                    desludging_other    VARCHAR(255) DEFAULT NULL,

                    -- Violations (JSON: {violation_key: bool})
                    violations          JSON DEFAULT NULL,

                    -- Summary
                    summary             VARCHAR(255) DEFAULT NULL,
                    summary_other       VARCHAR(255) DEFAULT NULL,

                    -- Recommendations (JSON array of selected items)
                    recommendations     JSON DEFAULT NULL,
                    recommendations_other VARCHAR(255) DEFAULT NULL,

                    created_at          DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at          DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

                    FOREIGN KEY (inspection_id) REFERENCES tbl_inspections(id) ON DELETE CASCADE,
                    UNIQUE KEY uq_inspection_checklist (inspection_id)
                )
            """))
            print("✓ Created tbl_inspection_checklist")

            trans.commit()
            print("✓ Migration complete")
        except Exception as e:
            trans.rollback()
            print(f"✗ Migration failed: {e}")
            raise


if __name__ == "__main__":
    run()
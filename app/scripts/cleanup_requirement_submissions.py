import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.business_record import BusinessRecord
from app.models.requirement import RequirementTemplate, RequirementSubmission

def run():
    db = SessionLocal()
    try:
        print("Cleaning up mismatched requirement submissions...")
        removed = 0

        submissions = db.query(RequirementSubmission).all()
        for sub in submissions:
            template = db.query(RequirementTemplate).filter(
                RequirementTemplate.id == sub.template_id
            ).first()

            if not template:
                db.delete(sub)
                removed += 1
                continue

            # If template is hauler-specific, check if business matches
            if template.hauler_type:
                business = db.query(BusinessRecord).filter(
                    BusinessRecord.id == sub.business_id
                ).first()
                if not business:
                    db.delete(sub)
                    removed += 1
                    continue

                biz_hauler = (
                    business.hauler_type.value
                    if hasattr(business.hauler_type, 'value')
                    else str(business.hauler_type)
                )
                if biz_hauler != template.hauler_type:
                    db.delete(sub)
                    removed += 1

        db.commit()
        print(f"✓ Removed {removed} mismatched submissions")
    except Exception as e:
        db.rollback()
        print(f"✗ Failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run()
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.requirement import RequirementTemplate, RequirementSubmission

DEFAULT_LABELS = [
    "DTI Registration",
    "Mayor's Permit",
    "Occupancy Permit",
    "Sanitation Permit",
    "Fire Safety Certificate",
    "Environmental Compliance Certificate",
]

def run():
    db = SessionLocal()
    try:
        # Find default templates
        defaults = db.query(RequirementTemplate).filter(
            RequirementTemplate.label.in_(DEFAULT_LABELS),
            RequirementTemplate.hauler_type == None,
        ).all()

        removed_templates = 0
        removed_submissions = 0

        for tmpl in defaults:
            # Delete all submissions for this template
            count = db.query(RequirementSubmission).filter(
                RequirementSubmission.template_id == tmpl.id
            ).delete()
            removed_submissions += count
            db.delete(tmpl)
            removed_templates += 1

        db.commit()
        print(f"✓ Removed {removed_templates} default templates")
        print(f"✓ Removed {removed_submissions} related submissions")
        print("Admin can now add requirements manually from Settings.")
    except Exception as e:
        db.rollback()
        print(f"✗ Failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run()
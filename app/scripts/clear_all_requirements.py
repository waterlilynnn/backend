import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.requirement import RequirementTemplate, RequirementSubmission

def run():
    db = SessionLocal()
    try:
        # Count before deletion
        templates_count = db.query(RequirementTemplate).count()
        submissions_count = db.query(RequirementSubmission).count()
        
        # Delete all submissions first
        db.query(RequirementSubmission).delete()
        
        # Delete all templates
        db.query(RequirementTemplate).delete()
        
        db.commit()
        
        print(f"✓ Removed {templates_count} requirement templates")
        print(f"✓ Removed {submissions_count} related submissions")
        print("✓ Database is now empty - no default requirements")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run()
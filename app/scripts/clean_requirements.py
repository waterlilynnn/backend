import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models.requirement import RequirementTemplate, RequirementSubmission

def run():
    db = SessionLocal()
    try:
        # Delete all existing requirements
        db.query(RequirementSubmission).delete()
        db.query(RequirementTemplate).delete()
        db.commit()
        print("✓ Cleared all existing requirements")
        
        # Create default global requirements
        default_requirements = [
            {"label": "DTI Registration", "description": "Business name registration certificate", "is_required": True, "sort_order": 1, "hauler_type": None},
            {"label": "Mayor's Permit", "description": "Business permit from city hall", "is_required": True, "sort_order": 2, "hauler_type": None},
            {"label": "Occupancy Permit", "description": "Building/space occupancy permit", "is_required": True, "sort_order": 3, "hauler_type": None},
            {"label": "Sanitation Permit", "description": "Health and sanitation clearance", "is_required": True, "sort_order": 4, "hauler_type": None},
            {"label": "Fire Safety Certificate", "description": "BFP fire safety inspection certificate", "is_required": True, "sort_order": 5, "hauler_type": None},
            {"label": "Environmental Compliance Certificate", "description": "ECC or CNC from DENR-EMB", "is_required": True, "sort_order": 6, "hauler_type": None},
        ]
        
        for req in default_requirements:
            template = RequirementTemplate(**req)
            db.add(template)
        
        db.commit()
        print(f"✓ Created {len(default_requirements)} default requirements")
        
    except Exception as e:
        db.rollback()
        print(f"✗ Failed: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    run()
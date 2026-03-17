import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal, engine, Base
from app.models.role import Role
from app.models.user import User
from app.core.security import get_password_hash
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def seed_database():
    """Seed the database with initial data"""
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()
    
    try:
        logger.info("=" * 50)
        logger.info("SEEDING DATABASE")
        logger.info("=" * 50)
        
        # Create roles
        logger.info("\nCreating roles...")
        roles = [
            {"name": "admin", "description": "Administrator - full access"},
            {"name": "staff", "description": "Staff - can manage business records and clearances"}
        ]
        
        for role_data in roles:
            existing = db.query(Role).filter(Role.name == role_data["name"]).first()
            if not existing:
                new_role = Role(
                    name=role_data["name"],
                    description=role_data["description"]
                )
                db.add(new_role)
                logger.info(f"Created role: {role_data['name']}")
            else:
                logger.info(f"Role already exists: {role_data['name']}")
        
        db.commit()
        
        # Get admin role
        admin_role = db.query(Role).filter(Role.name == "admin").first()
        if not admin_role:
            logger.error("Failed to create admin role!")
            return
        
        # Create admin user
        admin_email = "april.programming@gmail.com"
        admin = db.query(User).filter(User.email == admin_email).first()
        
        if not admin:
            admin = User(
                username="admin",
                full_name="Administrator",
                email=admin_email,
                hashed_password=get_password_hash("testadmin"),
                role_id=admin_role.id,
                is_active=True
            )
            db.add(admin)
            db.commit()
            logger.info(f"Created admin user: {admin_email}")
        else:
            logger.info(f"Admin user already exists: {admin_email}")
        
        staff_role = db.query(Role).filter(Role.name == "staff").first()
        if staff_role:
            staff_email = "staff@cenro.gov.ph"
            staff = db.query(User).filter(User.email == staff_email).first()
            
            if not staff:
                staff = User(
                    username="staff1",
                    full_name="CENRO Staff",
                    email=staff_email,
                    hashed_password=get_password_hash("teststaff"),
                    role_id=staff_role.id,
                    is_active=True,
                    created_by=admin.id if admin else None
                )
                db.add(staff)
                db.commit()
                logger.info(f"Created sample staff: {staff_email}")
        
        logger.info("\n" + "=" * 50)
        logger.info("DATABASE SEEDING COMPLETED SUCCESSFULLY")
        logger.info("=" * 50)
        
        # Show login credentials
        logger.info("\nLogin Credentials:")
        logger.info("   Admin:   april.programming@gmail.com / testadmin")
        logger.info("   Staff:   staff@cenro.gov.ph / teststaff")
        
    except Exception as e:
        logger.error(f"Seeding failed: {str(e)}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_database()
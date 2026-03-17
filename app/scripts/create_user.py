from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.models.user import User
from app.models.role import Role
import getpass

def create_user():
    db: Session = SessionLocal()

    try:
        print("=== Create Test User ===")

        username = input("Username: ").strip()
        email = input("Email: ").strip()
        password = getpass.getpass("Password: ")

        # check if user already exists
        existing = db.query(User).filter(
            (User.username == username) | (User.email == email)
        ).first()

        if existing:
            print("User already exists.")
            return

        # get default role 
        role = db.query(Role).filter(Role.name == "admin").first()
        if not role:
            print("Role 'Admin' not found.")
            return

        hashed_pw = User.hash_password(password)

        user = User(
            username=username,
            email=email,
            hashed_password=hashed_pw,
            role_id=role.id
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        print("User created successfully!")
        print(f"ID: {user.id}")
        print(f"Username: {user.username}")
        print(f"Email: {user.email}")
        print(f"Role: {role.name}")

    finally:
        db.close()

if __name__ == "__main__":
    create_user()

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.declarative import declarative_base
from app.core.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

engine = create_engine(DATABASE_URL, echo=True)
SessionLocal = sessionmaker(
    autocommit=False, 
    autoflush=False,
    bind=engine
)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from app.core.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD
import os

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

is_production = os.getenv("ENV", "development") == "production"

if is_production:
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        connect_args={"ssl": {"ssl_disabled": False}}
    )
else:
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
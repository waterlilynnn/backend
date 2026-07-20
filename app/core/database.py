import os
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD

DATABASE_URL = (
    f"mysql+pymysql://{DB_USER}:{DB_PASSWORD}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    f"?charset=utf8mb4"
)

_ENV = os.getenv("ENV", "development")

engine = create_engine(
    DATABASE_URL,
    echo=(_ENV == "development"),      
    pool_pre_ping=True,                 
    pool_recycle=1800,                  
    pool_timeout=30,
    pool_size=5,
    max_overflow=10,
    connect_args={
        "connect_timeout": 30,
        "read_timeout":    30,
        "write_timeout":   30,
    },
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
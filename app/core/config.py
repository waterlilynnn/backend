import os
from datetime import timedelta

# Load .env file ONLY in development
ENV = os.getenv("ENV", "development")
if ENV == "development":
    from dotenv import load_dotenv
    load_dotenv()

# ENV = os.getenv("ENV", "development") =

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306")) 
DB_NAME = os.getenv("DB_NAME", "db_cennro")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")

SECRET_KEY = os.getenv("SECRET_KEY", "TEST_SECRETKEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "cenro.cityoftagaytay@gmail.com")
SMTP_PASS = os.getenv("SMTP_PASS", "veyl wcof dlvq angu")
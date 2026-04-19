import os
from dotenv import load_dotenv

load_dotenv()

_raw_db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:123@localhost:5432/testdb",
)
# Принимаем и sync-URL из старых .env — переключаем драйвер на asyncpg.
if _raw_db_url.startswith("postgresql+psycopg2://"):
    DATABASE_URL = _raw_db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://", 1)
elif _raw_db_url.startswith("postgresql://"):
    DATABASE_URL = _raw_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    DATABASE_URL = _raw_db_url
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-secret-change-me")
SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() in {"1", "true", "yes"}

APP_BASE_URL = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")

EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@calendarproject.local")
EMAIL_SMTP_HOST = os.getenv("EMAIL_SMTP_HOST", "")
EMAIL_SMTP_PORT = int(os.getenv("EMAIL_SMTP_PORT", "587"))
EMAIL_SMTP_USER = os.getenv("EMAIL_SMTP_USER", "")
EMAIL_SMTP_PASSWORD = os.getenv("EMAIL_SMTP_PASSWORD", "")

VERIFY_TOKEN_TTL = 60 * 60 * 24 * 3       # 3 days
RESET_TOKEN_TTL = 60 * 60                 # 1 hour

UPLOAD_FOLDER = "static/user_avatars"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024

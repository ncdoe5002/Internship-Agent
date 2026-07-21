import os

from dotenv import load_dotenv

load_dotenv()


class Config:

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "postgresql://app:yourpassword@localhost:5432/pdfprocessor"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CELERY_BROKER_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")

    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", "uploads")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50 MB upload limit
    ALLOWED_EXTENSIONS = {"pdf", "xlsx", "docx"}

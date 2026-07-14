import os
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "careblink_fallback_secret_key_123")
    
    # Database settings
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "careblink")
    DB_SQLITE_PATH = os.getenv("DB_SQLITE_PATH", "careblink.db")
    
    # Server settings
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    FLASK_PORT = int(os.getenv("FLASK_PORT", 5000))
    DEBUG = (FLASK_ENV == "development")
    
    # Session & Security Settings
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = not DEBUG  # True in production
    SESSION_COOKIE_SAMESITE = "Lax"
    
    # Uploads config
    UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload

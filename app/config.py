import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./ce_guests.db")
    
    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me-in-production")
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "5"))
    REFRESH_TOKEN_EXPIRE_HOURS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_HOURS", "1"))
    TOKEN_CLEANUP_INTERVAL_SECONDS: int = int(os.getenv("TOKEN_CLEANUP_INTERVAL_SECONDS", "300"))
    
    # CORS
    CORS_ORIGINS: list[str] = [
        origin.strip() 
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]
    
    # Timezone
    TIMEZONE: str = os.getenv("TIMEZONE", "Europe/Moscow")
    
    # Server
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))
    
    # Autocomplete
    AUTOCOMPLETE_LOOKUP_LIMIT: int = int(os.getenv("AUTOCOMPLETE_LOOKUP_LIMIT", "100"))

    # External pass API (fallback when DB settings are empty)
    PASS_API_BASE_URL: str = os.getenv("PASS_API_BASE_URL", "")
    PASS_API_LOGIN: str = os.getenv("PASS_API_LOGIN", "")
    PASS_API_PASSWORD: str = os.getenv("PASS_API_PASSWORD", "")
    PASS_API_OBJECT: str = os.getenv("PASS_API_OBJECT", "")
    PASS_API_CORPA: str = os.getenv("PASS_API_CORPA", "")
    PASS_API_ORDER_TYPE: str = os.getenv("PASS_API_ORDER_TYPE", "1")
    PASS_API_BIRTHDAY: str = os.getenv("PASS_API_BIRTHDAY", "1917-11-07")
    PASS_API_BUILDIN: str = os.getenv("PASS_API_BUILDIN", "")
    PASS_API_FLOOR: str = os.getenv("PASS_API_FLOOR", "")
    PASS_API_OFFICE: str = os.getenv("PASS_API_OFFICE", "")
    PASS_API_CONTACT_EMAIL: str = os.getenv("PASS_API_CONTACT_EMAIL", "")
    PASS_API_CONTACT_PHONE: str = os.getenv("PASS_API_CONTACT_PHONE", "")
    PASS_API_POLL_DELAYS: str = os.getenv("PASS_API_POLL_DELAYS", "1,2,3,5,8")
    PASS_API_TIMEOUT_SECONDS: float = float(os.getenv("PASS_API_TIMEOUT_SECONDS", "15"))
    PASS_API_VERIFY_SSL: bool = os.getenv("PASS_API_VERIFY_SSL", "false").strip().lower() in {"1", "true", "yes"}


settings = Settings()

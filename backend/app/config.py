from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "AI-Finance"
    VERSION: str = "1.0.0"

    # Database Settings (PostgreSQL Docker: postgresql://postgres:postgres@db:5432/ai_finance)
    DATABASE_URL: str = "postgresql://postgres:postgres@db:5432/ai_finance"

    # Auth & JWT Settings
    SECRET_KEY: str = "ai-finance-secret-key-change-in-production-2026"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Initial Admin / Starter User
    ADMIN_EMAIL: Optional[str] = "admin@aifinance.com"
    ADMIN_PASSWORD: Optional[str] = "Admin123!"

    # 9router API Settings (OpenAI-compatible)
    LLM_BASE_URL: str = "http://localhost:8080/v1"
    LLM_API_KEY: str = "placeholder_key"
    LLM_MODEL_NAME: str = "gpt-4o"
    LLM_TIMEOUT: float = 60.0

    # Telegram Bot Integration
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # WhatsApp Cloud API Integration
    WHATSAPP_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_VERIFY_TOKEN: Optional[str] = "ai-finance-wa-verify"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

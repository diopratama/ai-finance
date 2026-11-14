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
    LLM_MAX_TOKENS: int = 2048
    LLM_REPORT_MAX_TOKENS: int = 4096
    LLM_MAX_CONTINUATIONS: int = 3
    LLM_MAX_CONCURRENCY: int = 2

    # Exa Search API (primary internet access; injected from Vault via ai-finance-secret)
    EXA_API_KEY: Optional[str] = ""
    EXA_TIMEOUT: float = 8.0

    # Financial Modeling Prep (FMP) & Twelve Data API
    FMP_API_KEY: str = ""
    TWELVE_DATA_API_KEY: str = ""

    # Multi-Agent Investment Research
    RECOMMENDATION_LIMIT: int = 8
    ENFORCE_RESEARCH_QUOTA: bool = False  # Free for all users for now; flip to True to enable quotas later
    DEFAULT_RESEARCH_QUOTA: int = 10
    RESEARCH_HISTORY_RETENTION: int = 50
    REDIS_URL: Optional[str] = ""

    # Telegram Bot Integration
    TELEGRAM_BOT_TOKEN: Optional[str] = None

    # WhatsApp Cloud API Integration
    WHATSAPP_TOKEN: Optional[str] = None
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_VERIFY_TOKEN: Optional[str] = "ai-finance-wa-verify"

    # Resend Email Integration
    RESEND_API_KEY: Optional[str] = None
    RESEND_FROM_EMAIL: str = "AI-Finance <onboarding@resend.dev>"

    # CORS
    ALLOWED_ORIGINS: str = "http://localhost:3001,http://127.0.0.1:3001,http://localhost:3000,http://127.0.0.1:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

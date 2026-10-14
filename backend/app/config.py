"""
GradeWise v3 — application config.
All settings come from environment variables (docker-compose or Droplet secrets).
Never import this from the frontend.
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # App
    APP_NAME: str = "GradeWise API"
    DEBUG: bool = False
    PORT: int = 8000
    DOCUMENT_DEMO: bool = False
    DEMO_PREVIEW_URL: str = ""  # Additional demo origin; never replaces production.
    DEMO_VERIFY_PROVIDERS: bool = False  # One-time deployment smoke check; makes real AI calls.
    CODE_EXECUTION_ENABLED: bool = True
    CODE_RUNNER_URL: str = ""  # Authenticated Vercel microVM bridge, never a browser credential.
    DEMO_VERIFY_CODE_RUNNER: bool = False
    DEMO_KEEPALIVE_ENABLED: bool = False
    DB_POOL_MAX_SIZE: int = 20
    DEMO_MAX_FILE_MB: int = 5
    DEMO_MAX_PDF_PAGES: int = 20
    DEMO_MAX_TEXT_CHARS: int = 60000
    DEMO_STORAGE_MB: int = 100
    # Restrict the public demo to explicitly invited Firebase users.
    # UIDs support existing testers; verified emails allow invitations before first sign-in.
    DEMO_ALLOWED_UIDS: str = ""
    DEMO_ALLOWED_EMAILS: str = ""
    DEMO_INSTRUCTOR_EMAILS: str = ""

    # Database — ONE Postgres for relational + vectors + graph
    DATABASE_URL: str = "postgresql+asyncpg://app_user:change_me@postgres:5432/feedback"
    REDIS_URL: str = "redis://redis:6379/0"

    # DigitalOcean Gradient (serverless inference)
    GRADIENT_API_KEY: str = ""
    GRADIENT_BASE_URL: str = "https://api.digitalocean.com/v1/inference"

    # Dedicated inference endpoint (Groq / any OpenAI-compatible)
    # When set, large submissions are routed here instead of Map-Reduce chunking.
    DEDICATED_INFERENCE_BASE_URL: Optional[str] = None
    DEDICATED_INFERENCE_TOKEN: Optional[str] = None
    DEDICATED_MODEL: str = "llama-3.3-70b-versatile"  # Groq model name
    DEDICATED_FALLBACK_BASE_URL: Optional[str] = None
    DEDICATED_FALLBACK_TOKEN: Optional[str] = None
    DEDICATED_FALLBACK_MODEL: Optional[str] = None
    DEDICATED_VISION_BASE_URL: Optional[str] = None
    DEDICATED_VISION_TOKEN: Optional[str] = None
    DEDICATED_VISION_MODEL: Optional[str] = None

    # Models
    GRADIENT_MODEL_SPECIALIST: str = "openai-gpt-oss-120b"
    GRADIENT_MODEL_JUDGE: str = "qwen3-32b"
    GRADIENT_MODEL_SENIOR: str = "openai-gpt-oss-120b"
    GRADIENT_MODEL_UTILITY: str = "openai-gpt-oss-20b"
    GRADIENT_EMBED_MODEL: str = "bge-m3"
    GRADIENT_RERANK_MODEL: str = "bge-reranker-v2-m3"
    GRADIENT_VISION_OCR_MODEL: Optional[str] = None  # cloud vision fallback
    VISUAL_EXTRACTION_ENABLED: bool = True
    # 0 means no cap. Positive values scan the whole PDF and send the most
    # visually relevant pages, rather than blindly taking the first N pages.
    VISUAL_EXTRACTION_MAX_PDF_PAGES: int = 20
    VISUAL_EXTRACTION_PAGE_DELAY_SECONDS: float = 6.0
    DIGITALOCEAN_WEB_SEARCH_AGENT_URL: Optional[str] = None
    DIGITALOCEAN_WEB_SEARCH_AGENT_KEY: Optional[str] = None
    INTERNET_PLAGIARISM_SEARCH_URL: Optional[str] = None
    INTERNET_PLAGIARISM_SEARCH_KEY: Optional[str] = None

    # Firebase (Auth + Storage ONLY)
    FIREBASE_PROJECT_ID: str = ""
    FIREBASE_CLIENT_EMAIL: str = ""
    FIREBASE_PRIVATE_KEY: str = ""
    FIREBASE_STORAGE_BUCKET: str = ""
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None
    FIREBASE_SERVICE_ACCOUNT_JSON: Optional[str] = None
    USE_MOCKS: bool = False

    # Stripe Payments & Subscription
    STRIPE_SECRET_KEY: Optional[str] = None
    STRIPE_PUBLISHABLE_KEY: Optional[str] = None
    STRIPE_WEBHOOK_SECRET: Optional[str] = None
    STRIPE_PRO_PRICE_ID: Optional[str] = None
    STRIPE_INSTITUTION_PRICE_ID: Optional[str] = None
    FRONTEND_URL: str = "http://localhost:3000"

    # Limits
    STUDENT_MAX_FILE_MB: int = 10
    INSTRUCTOR_BATCH_MAX_FILES: int = 30
    INSTRUCTOR_BATCH_MAX_MB: int = 100
    SANDBOX_TIMEOUT_SECONDS: int = 5
    SANDBOX_MEMORY_MB: int = 256

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, value):
        if isinstance(value, str) and value.lower() in {"release", "production", "prod"}:
            return False
        return value

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


settings = Settings()

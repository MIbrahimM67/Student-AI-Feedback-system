import os
from typing import Optional
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # App Settings
    APP_NAME: str = "AI-Powered Feedback System API"
    DEBUG: bool = True
    PORT: int = 8000
    
    # Mock Settings (extremely useful for offline development / no-credentials testing)
    USE_MOCKS: bool = True
    
    # Firebase Cloud Settings
    FIREBASE_SERVICE_ACCOUNT_PATH: Optional[str] = None
    FIREBASE_STORAGE_BUCKET: Optional[str] = None
    
    # DigitalOcean Inference / LLM Settings
    DIGITALOCEAN_API_KEY: Optional[str] = None
    DIGITALOCEAN_MODEL_PRIMARY: str = "meta-llama-3.3-70b-instruct"
    DIGITALOCEAN_MODEL_FAST: str = "meta-llama-3-8b-instruct"
    DIGITALOCEAN_EMBEDDING_MODEL: str = "bge-m3"
    DIGITALOCEAN_INFERENCE_BASE_URL: str = "https://api.digitalocean.com/v1/inference"
    
    # Tesseract OCR Settings
    TESSERACT_CMD: str = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    
    # Sandbox Settings
    SANDBOX_TIMEOUT: int = 5
    SANDBOX_MEMORY_LIMIT_MB: int = 256
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()

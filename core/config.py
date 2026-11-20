import os
from pathlib import Path
from typing import Any, Optional
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# Ensure Paddle and PaddleX caches are initialized inside workspace or /tmp for cloud containers
if os.environ.get("SPACE_ID") or not os.access(str(BASE_DIR), os.W_OK):
    cache_base = Path("/tmp/.cache")
else:
    cache_base = BASE_DIR / ".cache"

os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_base / "paddlex"))
os.environ.setdefault("PADDLE_HOME", str(cache_base / "paddle"))
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


class Settings(BaseSettings):
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_FALLBACK_API_KEY: str = ""
    GROQ_FALLBACK_MODEL: str = "qwen/qwen3.8-27b"
    GROQ_TIMEOUT_SECONDS: float = 60.0
    GROQ_MAX_RETRIES: int = 2
    GROQ_MAX_COMPLETION_TOKENS: int = 4096

    @model_validator(mode="before")
    @classmethod
    def resolve_fallback_groq_key(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("GROQ_FALLBACK_API_KEY"):
                for alt_key in ["GROQ_API_KEY_FALLBACK", "FALLBACK_GROQ_API_KEY", "GROQ_API_KEY_2", "GROQ_SECONDARY_API_KEY"]:
                    if data.get(alt_key):
                        data["GROQ_FALLBACK_API_KEY"] = data[alt_key]
                        break
        return data

    MAX_UPLOAD_SIZE_MB: int = 10
    OCR_LANGUAGE: str = "en"
    OCR_CONFIDENCE_THRESHOLD: float = 0.4
    DEFAULT_CURRENCY: str = "INR"

    # MongoDB Settings
    MONGODB_URI: str = "mongodb://localhost:27017/"
    MONGODB_DB_NAME: str = "receipt_db"
    MONGODB_COLLECTION: str = "Receipt_Extraction"
    MONGODB_ENABLED: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()

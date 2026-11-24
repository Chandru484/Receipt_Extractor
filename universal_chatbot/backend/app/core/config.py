import os
from pathlib import Path
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class ChatbotSettings(BaseSettings):
    """Configuration for Universal AI Chatbot Platform."""

    # Server Settings
    CHATBOT_ENV: str = "development"
    CHATBOT_HOST: str = "0.0.0.0"
    CHATBOT_PORT: int = 8080
    CHATBOT_SECRET_KEY: str = "chatbot-platform-default-dev-secret-key-32b"
    PLATFORM_ENCRYPTION_KEY: str = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    # Dedicated Chatbot AI Keys (Isolated from host applications)
    CHATBOT_GROQ_API_KEYS: str = Field(default="", description="Comma-separated Groq API keys for key rotation")
    CHATBOT_GROQ_MODEL: str = "llama-3.3-70b-versatile"
    CHATBOT_GROQ_TIMEOUT: float = 45.0
    CHATBOT_GROQ_MAX_RETRIES: int = 2

    # Secondary Multi-Provider Fallback (OpenRouter / DeepSeek / Mistral)
    CHATBOT_FALLBACK_PROVIDER: str = "openrouter"
    CHATBOT_FALLBACK_API_KEY: str = ""
    CHATBOT_FALLBACK_BASE_URL: str = "https://openrouter.ai/api/v1"
    CHATBOT_FALLBACK_MODEL: str = "meta-llama/llama-3.3-70b-instruct:free"

    # Primary MongoDB Database for Chatbot Platform
    CHATBOT_MONGODB_URI: str = Field(
        default="mongodb+srv://tekis_db_user:Test-123@cluster0.h0zex3e.mongodb.net/?retryWrites=true&w=majority",
        description="MongoDB connection URI"
    )
    CHATBOT_MONGODB_DB_NAME: str = "mongodb"
    CHATBOT_MONGODB_TIMEOUT_MS: int = 5000

    # Rate Limiting & Storage
    MAX_DOC_SIZE_MB: int = 15
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx", "txt", "csv", "xlsx"]
    CHATBOT_ALLOWED_ORIGINS: str = "*"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    def get_groq_keys(self) -> List[str]:
        """Return list of distinct, stripped Groq API keys."""
        if not self.CHATBOT_GROQ_API_KEYS:
            return []
        keys = [k.strip() for k in self.CHATBOT_GROQ_API_KEYS.split(",") if k.strip()]
        return keys


chatbot_settings = ChatbotSettings()

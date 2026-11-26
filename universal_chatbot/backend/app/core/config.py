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
    CHATBOT_GROQ_MODEL: str = "qwen/qwen3.8-27b"
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
        """Return list of distinct, stripped Groq API keys aggregated across all env sources."""
        raw_keys: List[str] = []

        # 1. Primary keys from CHATBOT_GROQ_API_KEYS
        if self.CHATBOT_GROQ_API_KEYS:
            raw_keys.extend([k.strip() for k in self.CHATBOT_GROQ_API_KEYS.split(",") if k.strip()])

        # 2. Check standard environment variables
        for var_name in ["GROQ_API_KEY", "GROQ_FALLBACK_API_KEY"]:
            val = os.getenv(var_name)
            if val and val.strip():
                raw_keys.append(val.strip())

        fallback_env = os.getenv("GROQ_FALLBACK_API_KEYS")
        if fallback_env:
            raw_keys.extend([k.strip() for k in fallback_env.split(",") if k.strip()])

        # 3. Check root application .env file if available
        root_env = BASE_DIR.parent / ".env"
        if root_env.exists():
            try:
                with open(root_env, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            var, val = line.split("=", 1)
                            var = var.strip()
                            val = val.strip().strip("'\"")
                            if var in ("GROQ_API_KEY", "GROQ_FALLBACK_API_KEY"):
                                if val:
                                    raw_keys.append(val)
                            elif var in ("GROQ_FALLBACK_API_KEYS", "CHATBOT_GROQ_API_KEYS"):
                                if val:
                                    raw_keys.extend([k.strip() for k in val.split(",") if k.strip()])
            except Exception:
                pass

        # Deduplicate while preserving priority order
        seen = set()
        deduped = []
        for k in raw_keys:
            if k not in seen and k.startswith("gsk_"):
                seen.add(k)
                deduped.append(k)
        return deduped


chatbot_settings = ChatbotSettings()

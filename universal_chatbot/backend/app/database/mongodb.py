import logging
from typing import Optional
from pymongo import MongoClient
from pymongo.database import Database

from universal_chatbot.backend.app.core.config import chatbot_settings

logger = logging.getLogger(__name__)

_client: Optional[MongoClient] = None


def get_mongo_client() -> Optional[MongoClient]:
    """Retrieve or initialize singleton MongoClient for the Chatbot Platform."""
    global _client
    if _client is None:
        try:
            _client = MongoClient(
                chatbot_settings.CHATBOT_MONGODB_URI,
                serverSelectionTimeoutMS=chatbot_settings.CHATBOT_MONGODB_TIMEOUT_MS,
                connectTimeoutMS=chatbot_settings.CHATBOT_MONGODB_TIMEOUT_MS,
                socketTimeoutMS=chatbot_settings.CHATBOT_MONGODB_TIMEOUT_MS * 2,
            )
        except Exception as exc:
            logger.error(f"Failed to initialize Chatbot Platform MongoDB client: {exc}")
            return None
    return _client


def get_chatbot_db() -> Optional[Database]:
    """Get the primary Chatbot Platform MongoDB database."""
    client = get_mongo_client()
    if client is None:
        return None
    return client[chatbot_settings.CHATBOT_MONGODB_DB_NAME]


def check_mongo_health() -> dict:
    """Diagnostic ping check for Chatbot Platform database."""
    try:
        client = get_mongo_client()
        if client is None:
            return {"status": "unreachable", "error": "Client not initialized"}
        client.admin.command("ping")
        return {
            "status": "connected",
            "database": chatbot_settings.CHATBOT_MONGODB_DB_NAME,
        }
    except Exception as exc:
        return {"status": "disconnected", "error": str(exc)}

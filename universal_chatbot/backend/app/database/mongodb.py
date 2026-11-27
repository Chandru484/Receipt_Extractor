import logging
import re
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


def get_project_db(project_id: Optional[str] = None) -> Optional[Database]:
    """
    Get or create an isolated, dedicated MongoDB database for a specific project/website.
    Each website/project gets its OWN distinct database in MongoDB:
    e.g. 'project_apex_portal_db', 'project_site_demo_db', etc.
    All data for that website is strictly contained inside that project's database.
    """
    client = get_mongo_client()
    if client is None:
        return None
    if not project_id:
        return client[chatbot_settings.CHATBOT_MONGODB_DB_NAME]
    clean_id = re.sub(r"[^\w\-]", "_", str(project_id).strip().lower())
    db_name = f"project_{clean_id}_db"
    return client[db_name]


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

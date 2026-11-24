from typing import Optional
from pymongo.collection import Collection

from universal_chatbot.backend.app.database.mongodb import get_chatbot_db


def get_collection(collection_name: str) -> Optional[Collection]:
    """Retrieve a specific collection from the Chatbot Platform database."""
    db = get_chatbot_db()
    if db is None:
        return None
    return db[collection_name]


# Platform collection getters
def get_tenants_collection() -> Optional[Collection]:
    return get_collection("tenants")


def get_websites_collection() -> Optional[Collection]:
    return get_collection("websites")


def get_admins_collection() -> Optional[Collection]:
    return get_collection("admins")


def get_visitor_sessions_collection() -> Optional[Collection]:
    return get_collection("visitor_sessions")


def get_conversations_collection() -> Optional[Collection]:
    return get_collection("conversations")


def get_messages_collection() -> Optional[Collection]:
    return get_collection("messages")


def get_knowledge_sources_collection() -> Optional[Collection]:
    return get_collection("knowledge_sources")


def get_document_chunks_collection() -> Optional[Collection]:
    return get_collection("document_chunks")


def get_user_documents_collection() -> Optional[Collection]:
    return get_collection("user_documents")


def get_app_connections_collection() -> Optional[Collection]:
    return get_collection("app_connections")


def get_support_handoffs_collection() -> Optional[Collection]:
    return get_collection("support_handoffs")


def get_analytics_events_collection() -> Optional[Collection]:
    return get_collection("analytics_events")

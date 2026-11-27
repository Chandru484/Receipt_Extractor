from typing import Optional
from pymongo.collection import Collection

from universal_chatbot.backend.app.database.mongodb import get_chatbot_db, get_project_db


def get_collection(collection_name: str, website_id: Optional[str] = None) -> Optional[Collection]:
    """Retrieve a specific collection from the project's dedicated isolated MongoDB database."""
    if website_id:
        db = get_project_db(website_id)
    else:
        db = get_chatbot_db()
    if db is None:
        return None
    return db[collection_name]


# Platform & Project collection getters
def get_tenants_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("tenants", website_id)


def get_websites_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("websites", website_id)


def get_admins_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("admins", website_id)


def get_visitor_sessions_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("visitor_sessions", website_id)


def get_conversations_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("conversations", website_id)


def get_messages_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("messages", website_id)


def get_knowledge_sources_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("knowledge_sources", website_id)


def get_document_chunks_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("document_chunks", website_id)


def get_user_documents_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("user_documents", website_id)


def get_app_connections_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("app_connections", website_id)


def get_support_handoffs_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("support_handoffs", website_id)


def get_analytics_events_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("analytics_events", website_id)


def get_orders_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("orders", website_id)


def get_users_collection(website_id: Optional[str] = None) -> Optional[Collection]:
    return get_collection("users", website_id)

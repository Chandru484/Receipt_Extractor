import logging
from pymongo import ASCENDING, DESCENDING, IndexModel
from universal_chatbot.backend.app.database import collections

logger = logging.getLogger(__name__)


def ensure_indexes():
    """Build and ensure all required MongoDB indexes across platform collections on startup."""
    try:
        # 1. Tenants Collection
        tenants = collections.get_tenants_collection()
        if tenants is not None:
            tenants.create_indexes([
                IndexModel([("tenant_id", ASCENDING)], unique=True),
                IndexModel([("created_at", DESCENDING)]),
            ])

        # 2. Websites Collection
        websites = collections.get_websites_collection()
        if websites is not None:
            websites.create_indexes([
                IndexModel([("website_id", ASCENDING)], unique=True),
                IndexModel([("tenant_id", ASCENDING), ("website_id", ASCENDING)]),
                IndexModel([("allowed_domains", ASCENDING)]),
            ])

        # 3. Admins Collection
        admins = collections.get_admins_collection()
        if admins is not None:
            admins.create_indexes([
                IndexModel([("email", ASCENDING)], unique=True),
                IndexModel([("tenant_id", ASCENDING)]),
            ])

        # 4. Visitor Sessions (with 7-day TTL expiration)
        sessions = collections.get_visitor_sessions_collection()
        if sessions is not None:
            sessions.create_indexes([
                IndexModel([("session_token", ASCENDING)], unique=True),
                IndexModel([("website_id", ASCENDING), ("session_token", ASCENDING)]),
                IndexModel([("expires_at", ASCENDING)], expireAfterSeconds=0),
            ])

        # 5. Conversations Collection
        convs = collections.get_conversations_collection()
        if convs is not None:
            convs.create_indexes([
                IndexModel([("conversation_id", ASCENDING)], unique=True),
                IndexModel([("tenant_id", ASCENDING), ("website_id", ASCENDING), ("user_id", ASCENDING)]),
                IndexModel([("website_id", ASCENDING), ("session_id", ASCENDING)]),
                IndexModel([("updated_at", DESCENDING)]),
            ])

        # 6. Messages Collection
        messages = collections.get_messages_collection()
        if messages is not None:
            messages.create_indexes([
                IndexModel([("conversation_id", ASCENDING), ("created_at", ASCENDING)]),
                IndexModel([("tenant_id", ASCENDING), ("created_at", DESCENDING)]),
            ])

        # 7. Knowledge Sources Collection
        knowledge = collections.get_knowledge_sources_collection()
        if knowledge is not None:
            knowledge.create_indexes([
                IndexModel([("website_id", ASCENDING), ("source_type", ASCENDING)]),
                IndexModel([("website_id", ASCENDING), ("url", ASCENDING)]),
            ])

        # 8. Document Chunks (for RAG Retrieval)
        chunks = collections.get_document_chunks_collection()
        if chunks is not None:
            chunks.create_indexes([
                IndexModel([("website_id", ASCENDING), ("document_id", ASCENDING)]),
                IndexModel([("tenant_id", ASCENDING), ("website_id", ASCENDING)]),
            ])

        # 9. User Uploaded Documents (strictly scoped by user/session)
        user_docs = collections.get_user_documents_collection()
        if user_docs is not None:
            user_docs.create_indexes([
                IndexModel([("document_id", ASCENDING)], unique=True),
                IndexModel([("website_id", ASCENDING), ("user_id", ASCENDING)]),
                IndexModel([("website_id", ASCENDING), ("session_id", ASCENDING)]),
            ])

        # 10. Application Connections
        app_conn = collections.get_app_connections_collection()
        if app_conn is not None:
            app_conn.create_indexes([
                IndexModel([("website_id", ASCENDING)], unique=True),
                IndexModel([("tenant_id", ASCENDING)]),
            ])

        # 11. Support Handoffs (Tawk.to)
        support = collections.get_support_handoffs_collection()
        if support is not None:
            support.create_indexes([
                IndexModel([("website_id", ASCENDING), ("created_at", DESCENDING)]),
            ])

        logger.info("Successfully verified all Chatbot Platform MongoDB indexes.")
    except Exception as exc:
        logger.warning(f"Could not build indexes during startup: {exc}")

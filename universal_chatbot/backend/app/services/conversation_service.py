import logging
import uuid
from typing import Any, Dict, List, Optional
from universal_chatbot.backend.app.database import collections
from universal_chatbot.backend.app.schemas.tenant_schema import get_ist_now_str

logger = logging.getLogger(__name__)


def get_or_create_conversation(
    website_id: str,
    tenant_id: str,
    conversation_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    language: str = "en",
) -> Dict[str, Any]:
    """Retrieve an active conversation or initialize a new one in MongoDB."""
    convs = collections.get_conversations_collection()
    now_str = get_ist_now_str()

    if conversation_id and convs is not None:
        existing = convs.find_one({"conversation_id": conversation_id, "website_id": website_id}, {"_id": 0})
        if existing:
            # Update active language if changed
            if language and existing.get("language") != language:
                convs.update_one(
                    {"conversation_id": conversation_id},
                    {"$set": {"language": language, "updated_at": now_str}}
                )
                existing["language"] = language
            return existing

    new_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    conv_doc = {
        "conversation_id": new_id,
        "website_id": website_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": session_id,
        "title": "New Conversation",
        "language": language,
        "message_count": 0,
        "created_at": now_str,
        "updated_at": now_str,
        "status": "active",
    }
    if convs is not None:
        convs.insert_one(conv_doc)

    return conv_doc


def save_message_interaction(
    conversation_id: str,
    website_id: str,
    tenant_id: str,
    user_message: str,
    bot_reply: str,
    language: str,
    source: str,
    citations: Optional[List[Dict[str, Any]]] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> str:
    """Save both user message and bot reply persistently into the messages collection."""
    messages = collections.get_messages_collection()
    convs = collections.get_conversations_collection()
    now_str = get_ist_now_str()

    message_id = f"msg_{uuid.uuid4().hex[:12]}"
    msg_doc = {
        "message_id": message_id,
        "conversation_id": conversation_id,
        "website_id": website_id,
        "tenant_id": tenant_id,
        "user_message": user_message,
        "bot_reply": bot_reply,
        "language": language,
        "source": source,
        "citations": citations or [],
        "meta": meta or {},
        "created_at": now_str,
    }
    if messages is not None:
        messages.insert_one(msg_doc)

    if convs is not None:
        # Update message count and latest title
        convs.update_one(
            {"conversation_id": conversation_id},
            {
                "$inc": {"message_count": 2},
                "$set": {
                    "updated_at": now_str,
                    "title": user_message[:40] + ("..." if len(user_message) > 40 else ""),
                },
            },
        )

    return message_id


def get_conversation_history(conversation_id: str, limit: int = 20) -> List[Dict[str, str]]:
    """Retrieve message history formatted for LLM context (role: user, role: assistant)."""
    messages = collections.get_messages_collection()
    if messages is None:
        return []

    cursor = messages.find(
        {"conversation_id": conversation_id},
        {"user_message": 1, "bot_reply": 1, "_id": 0}
    ).sort("created_at", 1).limit(limit)

    formatted: List[Dict[str, str]] = []
    for m in cursor:
        if m.get("user_message"):
            formatted.append({"role": "user", "content": m["user_message"]})
        if m.get("bot_reply"):
            formatted.append({"role": "assistant", "content": m["bot_reply"]})

    return formatted


def record_support_handoff(
    website_id: str,
    tenant_id: str,
    conversation_id: Optional[str],
    user_query: str,
    user_id: Optional[str] = None,
) -> str:
    """Log a Tawk.to human escalation event in MongoDB."""
    support = collections.get_support_handoffs_collection()
    now_str = get_ist_now_str()
    handoff_id = f"sup_{uuid.uuid4().hex[:12]}"

    doc = {
        "handoff_id": handoff_id,
        "website_id": website_id,
        "tenant_id": tenant_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "user_query": user_query,
        "created_at": now_str,
        "status": "initiated",
    }
    if support is not None:
        support.insert_one(doc)

    return handoff_id

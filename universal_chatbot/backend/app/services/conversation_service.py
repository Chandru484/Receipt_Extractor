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
    package_id: Optional[str] = None,
    language: str = "en",
) -> Dict[str, Any]:
    """Retrieve an active conversation or initialize a new one in MongoDB."""
    convs = collections.get_conversations_collection()
    now_str = get_ist_now_str()

    if conversation_id and convs is not None:
        existing = convs.find_one({"conversation_id": conversation_id, "website_id": website_id}, {"_id": 0})
        if existing:
            updates = {}
            # Update active language if changed
            if language and existing.get("language") != language:
                updates["language"] = language
                existing["language"] = language
            if package_id and existing.get("package_id") != package_id:
                updates["package_id"] = package_id
                existing["package_id"] = package_id
            if user_id and existing.get("user_id") != user_id:
                updates["user_id"] = user_id
                existing["user_id"] = user_id
            if updates:
                updates["updated_at"] = now_str
                convs.update_one({"conversation_id": conversation_id}, {"$set": updates})
            return existing

    new_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    conv_doc = {
        "conversation_id": new_id,
        "website_id": website_id,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "package_id": package_id,
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


def get_conversation_history(conversation_id: str, limit: int = 6) -> List[Dict[str, str]]:
    """Retrieve the most recent message history formatted for LLM context (role: user, role: assistant)."""
    messages = collections.get_messages_collection()
    if messages is None:
        return []

    # Fetch the most recent interactions in reverse chronological order
    recent_docs = list(messages.find(
        {"conversation_id": conversation_id},
        {"user_message": 1, "bot_reply": 1, "_id": 0}
    ).sort("created_at", -1).limit(limit))

    # Reverse to chronological order (oldest to newest among the recent window)
    recent_docs.reverse()

    formatted: List[Dict[str, str]] = []
    for m in recent_docs:
        if m.get("user_message"):
            formatted.append({"role": "user", "content": m["user_message"][:400]})
        if m.get("bot_reply"):
            # Compact older bot replies so that huge past tables don't exhaust TPM
            bot_text = m["bot_reply"]
            if len(bot_text) > 400:
                bot_text = bot_text[:400] + "..."
            formatted.append({"role": "assistant", "content": bot_text})

    return formatted


def delete_message(message_id: str) -> bool:
    """Delete a message interaction from MongoDB and decrement conversation message count."""
    messages = collections.get_messages_collection()
    convs = collections.get_conversations_collection()
    if messages is None:
        return False

    msg = messages.find_one({"message_id": message_id})
    if not msg:
        return False

    conv_id = msg.get("conversation_id")
    result = messages.delete_one({"message_id": message_id})
    if result.deleted_count > 0:
        if convs is not None and conv_id:
            convs.update_one(
                {"conversation_id": conv_id, "message_count": {"$gt": 0}},
                {"$inc": {"message_count": -2}}
            )
        return True
    return False


def update_user_message(message_id: str, new_user_message: str) -> bool:
    """Update a user's prompt text in an existing message interaction."""
    messages = collections.get_messages_collection()
    if messages is None:
        return False

    now_str = get_ist_now_str()
    result = messages.update_one(
        {"message_id": message_id},
        {
            "$set": {
                "user_message": new_user_message,
                "is_edited": True,
                "edited_at": now_str,
            }
        }
    )
    return result.matched_count > 0


def update_bot_reply(message_id: str, new_bot_reply: str) -> bool:
    """Update the bot's reply text when a message is re-generated."""
    messages = collections.get_messages_collection()
    if messages is None:
        return False

    now_str = get_ist_now_str()
    result = messages.update_one(
        {"message_id": message_id},
        {
            "$set": {
                "bot_reply": new_bot_reply,
                "updated_at": now_str,
            }
        }
    )
    return result.matched_count > 0


def list_user_conversations(
    website_id: str,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
    limit: int = 30,
) -> List[Dict[str, Any]]:
    """Retrieve past conversations for a user or visitor session, newest first."""
    convs = collections.get_conversations_collection()
    if convs is None:
        return []

    clauses: List[Dict[str, Any]] = [
        {"website_id": website_id},
        {"status": {"$ne": "deleted"}},
    ]
    if user_id:
        clauses.append({"$or": [{"user_id": user_id}, {"session_id": session_id}]})
    elif session_id:
        clauses.append({"session_id": session_id})

    query = {"$and": clauses} if len(clauses) > 1 else clauses[0]
    cursor = convs.find(query, {"_id": 0}).sort("updated_at", -1).limit(limit)
    conv_list = list(cursor)

    # Filter out empty conversations that had no messages
    return [c for c in conv_list if c.get("message_count", 0) > 0]


def get_conversation_detail(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve conversation metadata and full structured message history."""
    convs = collections.get_conversations_collection()
    messages = collections.get_messages_collection()
    if convs is None or messages is None:
        return None

    conv = convs.find_one({"conversation_id": conversation_id}, {"_id": 0})
    if not conv:
        return None

    msg_cursor = messages.find(
        {"conversation_id": conversation_id},
        {"_id": 0}
    ).sort("created_at", 1).limit(100)

    conv["messages"] = list(msg_cursor)
    conv["count"] = len(conv["messages"])
    return conv


def delete_conversation(conversation_id: str) -> bool:
    """Delete a conversation and all its messages permanently."""
    convs = collections.get_conversations_collection()
    messages = collections.get_messages_collection()
    if convs is None or messages is None:
        return False

    messages.delete_many({"conversation_id": conversation_id})
    res = convs.delete_one({"conversation_id": conversation_id})
    return res.deleted_count > 0




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


def ensure_user_record(
    website_id: str,
    user_id: str,
    role: Optional[str] = None,
    package_id: Optional[str] = None,
) -> None:
    """Store or update user profile and activity timestamp in the MongoDB users collection."""
    if not user_id:
        return
    users_col = collections.get_collection("users")
    if users_col is not None:
        now_str = get_ist_now_str()
        users_col.update_one(
            {"website_id": website_id, "user_id": user_id},
            {
                "$setOnInsert": {
                    "user_id": user_id,
                    "website_id": website_id,
                    "created_at": now_str,
                },
                "$set": {
                    "role": role or "user",
                    "package_id": package_id,
                    "last_active_at": now_str,
                },
                "$inc": {"interaction_count": 1},
            },
            upsert=True,
        )

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Header, Query, status
from universal_chatbot.backend.app.schemas.chat_schema import ChatMessageRequest, ChatMessageResponse, EditMessageRequest
from universal_chatbot.backend.app.services.chat_orchestrator import chat_orchestrator
from universal_chatbot.backend.app.services.conversation_service import (
    get_conversation_history,
    get_conversation_detail,
    list_user_conversations,
    delete_conversation,
    delete_message,
    update_user_message,
)
from universal_chatbot.backend.app.services.tenant_service import get_website_by_id
from universal_chatbot.backend.app.services.voice_service import prewarm_tts_cache

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/message", response_model=ChatMessageResponse, summary="Send message to AI Chatbot")
def send_chat_message(request: ChatMessageRequest, background_tasks: BackgroundTasks):
    """Process a user question, orchestrate retrieval and AI response, and persist conversation."""
    try:
        effective_user_id = request.admin_id or request.user_id
        if request.admin_id and not request.role:
            request.role = "admin"
        response = chat_orchestrator.process_message(request, verified_user_id=effective_user_id)
        # Pre-synthesize and warm audio cache in background immediately
        if response and response.reply:
            background_tasks.add_task(prewarm_tts_cache, response.reply, response.language)
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chatbot failed to process message: {str(exc)}"
        )


@router.get("/conversations", summary="List past conversations for user or session")
def list_conversations(
    website_id: str = Query(..., description="Website identifier"),
    user_id: Optional[str] = Query(None, description="Optional logged in user ID"),
    session_id: Optional[str] = Query(None, description="Visitor session ID"),
    limit: int = Query(30, ge=1, le=100, description="Max conversations to return"),
):
    """List previous conversation sessions for the visitor/user."""
    convs = list_user_conversations(
        website_id=website_id,
        user_id=user_id,
        session_id=session_id,
        limit=limit,
    )
    return {
        "website_id": website_id,
        "conversations": convs,
        "count": len(convs),
    }


@router.get("/conversations/{conversation_id}", summary="Get conversation history")
def get_chat_history(conversation_id: str, limit: int = 50):
    """Retrieve full structured message history for a conversation ID."""
    detail = get_conversation_detail(conversation_id)
    if detail:
        return detail

    # Fallback to LLM formatted history if metadata document missing
    history = get_conversation_history(conversation_id, limit=limit)
    return {
        "conversation_id": conversation_id,
        "title": "Conversation",
        "messages": history,
        "count": len(history),
    }


@router.delete("/conversations/{conversation_id}", summary="Delete an entire conversation")
def remove_conversation(conversation_id: str):
    """Delete a conversation and all its messages."""
    success = delete_conversation(conversation_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation '{conversation_id}' not found."
        )
    return {"success": True, "conversation_id": conversation_id}



@router.get("/widget-config/{website_id}", summary="Get widget public configuration")
def get_widget_configuration(website_id: str):
    """Retrieve branding, theme, languages, and settings for the embeddable widget."""
    site = get_website_by_id(website_id)
    if not site:
        # Return fallback configuration
        return {
            "website_id": website_id,
            "bot_name": "Assistant",
            "primary_color": "#2563eb",
            "welcome_message_en": "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?",
            "welcome_message_ta": "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?",
            "default_language": "en",
            "available_languages": ["en", "ta"],
            "allow_file_uploads": True,
            "allow_voice_input": True,
            "allow_speech_output": True,
            "enable_tawk_to": False,
        }
    return {
        "website_id": website_id,
        **site.get("widget_config", {})
    }


@router.delete("/messages/{message_id}", summary="Delete message from chat history")
def delete_chat_message(message_id: str):
    """Delete a specific message interaction from MongoDB conversation history."""
    success = delete_message(message_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{message_id}' not found or already deleted."
        )
    return {"success": True, "message_id": message_id}


@router.put("/messages/{message_id}", summary="Edit existing user message")
def edit_chat_message(message_id: str, request: EditMessageRequest):
    """Edit the user's prompt text in an existing message interaction."""
    success = update_user_message(message_id, request.message)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Message '{message_id}' not found."
        )
    return {"success": True, "message_id": message_id, "updated_message": request.message}


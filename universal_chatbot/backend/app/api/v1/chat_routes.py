from typing import Any, Dict
from fastapi import APIRouter, BackgroundTasks, HTTPException, Header, status
from universal_chatbot.backend.app.schemas.chat_schema import ChatMessageRequest, ChatMessageResponse
from universal_chatbot.backend.app.services.chat_orchestrator import chat_orchestrator
from universal_chatbot.backend.app.services.conversation_service import get_conversation_history
from universal_chatbot.backend.app.services.tenant_service import get_website_by_id
from universal_chatbot.backend.app.services.voice_service import prewarm_tts_cache

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/message", response_model=ChatMessageResponse, summary="Send message to AI Chatbot")
def send_chat_message(request: ChatMessageRequest, background_tasks: BackgroundTasks):
    """Process a user question, orchestrate retrieval and AI response, and persist conversation."""
    try:
        response = chat_orchestrator.process_message(request, verified_user_id=request.user_id)
        # Pre-synthesize and warm audio cache in background immediately
        if response and response.reply:
            background_tasks.add_task(prewarm_tts_cache, response.reply, response.language)
        return response
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chatbot failed to process message: {str(exc)}"
        )


@router.get("/conversations/{conversation_id}", summary="Get conversation history")
def get_chat_history(conversation_id: str, limit: int = 50):
    """Retrieve previous message exchanges for an existing conversation ID."""
    history = get_conversation_history(conversation_id, limit=limit)
    return {
        "conversation_id": conversation_id,
        "messages": history,
        "count": len(history),
    }


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

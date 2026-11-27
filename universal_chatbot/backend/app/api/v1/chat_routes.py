import re
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Header, Query, status
from universal_chatbot.backend.app.schemas.chat_schema import (
    ChatMessageRequest,
    ChatMessageResponse,
    EditMessageRequest,
    ChatInitRequest,
    ChatInitResponse,
)
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
from universal_chatbot.backend.app.services.package_service import package_service
from universal_chatbot.backend.app.services.voice_service import prewarm_tts_cache

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("/message", response_model=ChatMessageResponse, summary="Send message to AI Chatbot")
def send_chat_message(
    request: ChatMessageRequest,
    background_tasks: BackgroundTasks,
    website_id: Optional[str] = Query(None, description="Optional project/website ID from URL query"),
    project_id: Optional[str] = Query(None, description="Optional project/website ID from URL query"),
    package_id: Optional[str] = Query(None, description="Optional package identifier from URL query"),
):
    """Process a user question, orchestrate retrieval and AI response, and persist conversation."""
    try:
        # Allow URL query param project_id or website_id to override or provide the project identifier
        if project_id:
            request.website_id = project_id
        elif website_id:
            request.website_id = website_id
        elif not request.website_id:
            request.website_id = "site_demo"

        # Sanitize and normalize language to supported codes ('en', 'ta')
        if not request.language:
            request.language = "en"
        elif str(request.language).lower().startswith("ta"):
            request.language = "ta"
        else:
            request.language = "en"

        if package_id and not request.package_id:
            request.package_id = package_id

        effective_user_id = request.admin_id or request.user_id
        if request.admin_id and not request.role:
            request.role = "admin"

        if effective_user_id:
            try:
                package_service.record_candidate(
                    project_id=request.website_id,
                    role=request.role or "user",
                    candidate_id=effective_user_id,
                )
            except Exception:
                pass

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


@router.post("/init", response_model=ChatInitResponse, summary="Initialize or resume chat session on widget open")
def init_chat_session(payload: ChatInitRequest):
    """
    Called when a user opens/clicks the chatbot widget.
    1. Identifies user_id, package_id, role, website_id.
    2. Builds deterministic conversation_id = conv_{package_id}_{user_id}.
    3. Finds if the user is new or has already made conversations.
    4. Auto-records candidate profile in MongoDB collection.
    5. Returns conversation status, history visibility flag, messages, and role suggestions.
    """
    target_site = payload.website_id or payload.project_id or "site_demo"
    target_uid = payload.user_id or payload.admin_id
    target_role = (payload.role or "user").strip().lower()
    if payload.admin_id and target_role != "admin":
        target_role = "admin"
    if target_role not in ("admin", "worker", "user", "guest"):
        target_role = "user"

    target_pkg = payload.package_id or "default_pkg"

    # Auto-record candidate in the role's collection if user logged in
    if target_uid:
        try:
            package_service.record_candidate(
                project_id=target_site,
                role=target_role,
                candidate_id=target_uid,
            )
        except Exception:
            pass

    # Build deterministic conversation_id
    if target_uid:
        clean_pkg = re.sub(r"[^\w\-]", "_", str(target_pkg).strip())
        clean_uid = re.sub(r"[^\w\-]", "_", str(target_uid).strip())
        conv_id = f"conv_{clean_pkg}_{clean_uid}"
    else:
        clean_sess = re.sub(r"[^\w\-]", "_", str(payload.session_id or "visitor").strip())
        conv_id = f"conv_guest_{clean_sess}"

    # Check for past conversation messages
    has_history = False
    is_new_user = True
    messages: List[Dict[str, Any]] = []

    detail = get_conversation_detail(conv_id, website_id=target_site)
    if detail and detail.get("messages") and len(detail["messages"]) > 0:
        has_history = True
        is_new_user = False
        messages = detail["messages"]
    elif target_uid:
        past_convs = list_user_conversations(website_id=target_site, user_id=target_uid, limit=5)
        if past_convs and len(past_convs) > 0:
            has_history = True
            is_new_user = False
            first_conv_id = past_convs[0].get("conversation_id")
            if first_conv_id:
                past_detail = get_conversation_detail(first_conv_id, website_id=target_site)
                if past_detail and past_detail.get("messages") and len(past_detail["messages"]) > 0:
                    messages = past_detail["messages"]
                    conv_id = first_conv_id

    # Fetch role suggested questions
    sugg = package_service.get_candidate_suggestions(
        project_id=target_site,
        role=target_role,
        candidate_id=target_uid,
    )

    return ChatInitResponse(
        status="success",
        website_id=target_site,
        user_id=target_uid,
        role=target_role,
        package_id=target_pkg,
        conversation_id=conv_id,
        is_new_user=is_new_user,
        has_history=has_history,
        message_count=len(messages),
        messages=messages,
        suggested_questions=sugg.suggested_questions if sugg else [],
        package_name=sugg.package_name if sugg else None,
    )


@router.get("/history", summary="Get conversation history by package_id and user_id")
def get_history_by_package_and_user(
    package_id: str = Query(..., description="Package identifier (e.g. 'pkg_basic')"),
    user_id: Optional[str] = Query(None, description="Logged in user ID"),
    admin_id: Optional[str] = Query(None, description="Logged in admin ID"),
    website_id: str = Query("site_demo", description="Website / project identifier"),
    limit: int = Query(50, ge=1, le=200, description="Max messages to retrieve"),
):
    """
    Retrieve past conversation messages for a specific user and package combination.
    When a user re-opens the chatbot with the same user_id and package_id, this endpoint
    returns their previous chat history so it can be restored and displayed.
    """
    target_uid = user_id or admin_id
    if not target_uid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either user_id or admin_id must be provided to fetch conversation history."
        )

    clean_pkg = re.sub(r"[^\w\-]", "_", str(package_id).strip())
    clean_uid = re.sub(r"[^\w\-]", "_", str(target_uid).strip())
    conv_id = f"conv_{clean_pkg}_{clean_uid}"

    detail = get_conversation_detail(conv_id)
    if detail:
        detail["package_id"] = package_id
        detail["user_id"] = target_uid
        return detail

    return {
        "conversation_id": conv_id,
        "website_id": website_id,
        "package_id": package_id,
        "user_id": target_uid,
        "title": "New Conversation",
        "messages": [],
        "count": 0,
    }


@router.get("/conversations", summary="List past conversations for user or session")
def list_conversations(
    website_id: Optional[str] = Query(None, description="Website identifier"),
    project_id: Optional[str] = Query(None, description="Project identifier"),
    user_id: Optional[str] = Query(None, description="Optional logged in user ID"),
    session_id: Optional[str] = Query(None, description="Visitor session ID"),
    limit: int = Query(30, ge=1, le=100, description="Max conversations to return"),
):
    """List previous conversation sessions for the visitor/user."""
    target_site = website_id or project_id or "site_demo"
    convs = list_user_conversations(
        website_id=target_site,
        user_id=user_id,
        session_id=session_id,
        limit=limit,
    )
    return {
        "website_id": target_site,
        "conversations": convs,
        "count": len(convs),
    }


@router.get("/conversations/{conversation_id}", summary="Get conversation history")
def get_chat_history(
    conversation_id: str,
    website_id: Optional[str] = Query(None, description="Optional website ID for project database routing"),
    limit: int = 50,
):
    """Retrieve full structured message history for a conversation ID."""
    detail = get_conversation_detail(conversation_id, website_id=website_id)
    if detail:
        return detail

    # Fallback to LLM formatted history if metadata document missing
    history = get_conversation_history(conversation_id, limit=limit, website_id=website_id)
    return {
        "conversation_id": conversation_id,
        "title": "Conversation",
        "messages": history,
        "count": len(history),
    }


@router.delete("/conversations/{conversation_id}", summary="Delete an entire conversation")
def remove_conversation(
    conversation_id: str,
    website_id: Optional[str] = Query(None, description="Optional website ID for project database routing"),
):
    """Delete a conversation and all its messages."""
    success = delete_conversation(conversation_id, website_id=website_id)
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
            "welcome_message_en": "Hello! How can I help you today?",
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


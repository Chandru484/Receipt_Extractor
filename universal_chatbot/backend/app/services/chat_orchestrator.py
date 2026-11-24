import logging
import re
from typing import Any, Dict, List, Optional
from universal_chatbot.backend.app.ai.multi_provider import ai_engine
from universal_chatbot.backend.app.schemas.chat_schema import (
    ChatMessageRequest,
    ChatMessageResponse,
    SourceCitation,
)
from universal_chatbot.backend.app.schemas.tenant_schema import get_ist_now_str
from universal_chatbot.backend.app.services.tenant_service import get_website_by_id
from universal_chatbot.backend.app.services.conversation_service import (
    get_or_create_conversation,
    get_conversation_history,
    save_message_interaction,
    record_support_handoff,
)

logger = logging.getLogger(__name__)

HUMAN_SUPPORT_KEYWORDS = [
    "human", "agent", "support", "talk to human", "customer care", "representative",
    "உதவியாளர்", "மனிதர்", "தொடர்பு", "வாடிக்கையாளர் சேவை"
]


def _build_system_prompt(bot_name: str, language: str) -> str:
    if language == "ta":
        return f"""நீங்கள் '{bot_name}' என்ற அதிகாரப்பூர்வ AI உதவியாளர்.
பயனரின் கேள்விகளுக்குத் தெளிவான, சுருக்கமான, கண்ணியமான மற்றும் துல்லியமான தமிழில் பதிலளிக்கவும்.
பயனர் தமிழில் கேட்டால் கட்டாயமாக தமிழிலேயே பதிலளிக்கவும்.
விடை தெரியாத விஷயங்களுக்கு தவறான தகவல்களை உருவாக்க வேண்டாம்.
தேவைப்பட்டால் மனித உதவியாளரை அணுக பரிந்துரைக்கவும்."""
    else:
        return f"""You are '{bot_name}', the official AI conversational assistant.
Provide helpful, concise, professional, and accurate answers to the user's questions.
If the user asks in English, respond in clear English.
If you do not know the answer based on authorized information, politely state so without hallucinating.
Offer human support assistance whenever appropriate."""


class ChatOrchestrator:
    """Orchestrates end-to-end chat flow: context retrieval, intent routing, AI response generation, and persistence."""

    def process_message(
        self,
        request: ChatMessageRequest,
        verified_user_id: Optional[str] = None,
    ) -> ChatMessageResponse:
        # 1. Resolve website configuration & tenant
        site = get_website_by_id(request.website_id)
        if not site:
            # Fallback mock for demo/sandbox if site not registered yet
            site = {
                "website_id": request.website_id,
                "tenant_id": "ten_default",
                "name": "Default Platform Assistant",
                "widget_config": {
                    "bot_name": "Universal Assistant",
                    "enable_tawk_to": True,
                    "tawk_to_property_id": None,
                },
            }

        tenant_id = site.get("tenant_id", "ten_default")
        widget_cfg = site.get("widget_config", {})
        bot_name = widget_cfg.get("bot_name", "Assistant")

        # 2. Check for explicit human support request
        user_msg_lower = request.message.lower().strip()
        needs_escalation = any(k in user_msg_lower for k in HUMAN_SUPPORT_KEYWORDS)

        if needs_escalation and widget_cfg.get("enable_tawk_to"):
            handoff_id = record_support_handoff(
                website_id=request.website_id,
                tenant_id=tenant_id,
                conversation_id=request.conversation_id,
                user_query=request.message,
                user_id=verified_user_id,
            )
            reply = (
                "மனித வாடிக்கையாளர் சேவை முகவரிடம் உங்களை இணைக்கிறேன். தயவுசெய்து காத்திருக்கவும்..."
                if request.language == "ta"
                else "I am transferring you to a human support agent right now. Please hold on..."
            )
            return ChatMessageResponse(
                conversation_id=request.conversation_id or "conv_support",
                message_id=handoff_id,
                reply=reply,
                language=request.language,
                source="handoff",
                citations=[],
                escalate_to_human=True,
                tawk_property_id=widget_cfg.get("tawk_to_property_id"),
                created_at=get_ist_now_str(),
            )

        # 3. Get or create conversation in MongoDB
        conv = get_or_create_conversation(
            website_id=request.website_id,
            tenant_id=tenant_id,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            user_id=verified_user_id,
            language=request.language,
        )
        active_conv_id = conv["conversation_id"]

        # 4. Load past context history (up to last 10 messages)
        history = get_conversation_history(active_conv_id, limit=10)
        history.append({"role": "user", "content": request.message})

        # 5. Build prompt & call MultiProvider AI Engine
        system_prompt = _build_system_prompt(bot_name, request.language)
        ai_res = ai_engine.generate_chat_response(
            messages=history,
            system_prompt=system_prompt,
            language=request.language,
        )

        bot_reply = ai_res.get("reply", "")

        # 6. Save message interaction into MongoDB
        msg_id = save_message_interaction(
            conversation_id=active_conv_id,
            website_id=request.website_id,
            tenant_id=tenant_id,
            user_message=request.message,
            bot_reply=bot_reply,
            language=request.language,
            source="general",
            meta={
                "provider": ai_res.get("provider"),
                "model": ai_res.get("model"),
                "latency": ai_res.get("latency"),
                "tokens": ai_res.get("tokens_used"),
            },
        )

        return ChatMessageResponse(
            conversation_id=active_conv_id,
            message_id=msg_id,
            reply=bot_reply,
            language=request.language,
            source="general",
            citations=[],
            escalate_to_human=False,
            created_at=get_ist_now_str(),
        )


chat_orchestrator = ChatOrchestrator()

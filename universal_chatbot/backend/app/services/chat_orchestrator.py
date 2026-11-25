import json
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
from universal_chatbot.backend.app.services.rag_service import rag_service
from universal_chatbot.backend.app.application_adapters.mongodb_adapter import app_mongo_adapter

logger = logging.getLogger(__name__)

HUMAN_SUPPORT_KEYWORDS = [
    "human", "agent", "support", "talk to human", "customer care", "representative",
    "உதவியாளர்", "மனிதர்", "தொடர்பு", "வாடிக்கையாளர் சேவை"
]


def _build_system_prompt(bot_name: str, language: str, context_blocks: List[str]) -> str:
    context_str = "\n\n".join(context_blocks) if context_blocks else ""

    if language == "ta":
        base_prompt = f"""நீங்கள் '{bot_name}' என்ற அதிகாரப்பூர்வ AI உதவியாளர்.
கட்டாயம்: பயனர் எந்த மொழியில் கேட்டாலும் (ஆங்கிலம் அல்லது Tanglish உட்பட), நீங்கள் கட்டாயமாக தெளிவான, சுருக்கமான தமிழில் மட்டுமே பதிலளிக்க வேண்டும்.
தகவல்களைச் சுருக்கமாகவும் தெளிவான புள்ளிகளாகவும் (bullet points) வழங்கவும். 10-க்கும் மேற்பட்ட பொருட்கள் இருந்தால், முக்கிய விவரங்களையும் மொத்தத் தொகையையும் சுருக்கமாகக் காட்டவும் (பயனர் அனைத்து வரிகளையும் கேட்டால் தவிர).
விடை தெரியாத விஷயங்களுக்கு தவறான தகவல்களை உருவாக்க வேண்டாம்."""
        if context_str:
            base_prompt += f"""\n\nபின்வரும் அங்கீகரிக்கப்பட்ட தகவல் மற்றும் ஆவணங்களின் அடிப்படையில் பதிலளிக்கவும்:\n{context_str}"""
    else:
        base_prompt = f"""You are '{bot_name}', the official AI conversational assistant.
MANDATORY LANGUAGE RULE: The user has selected English. You MUST respond strictly in clear English, even if the user writes in Tanglish (e.g., 'indha pdf ai patri sol') or another language.
Keep your answers concise, well-structured, and easy to read using short bullet points or compact summary tables. If a document has many line items (e.g. >10 items), summarize the key highlights, totals, and top items instead of dumping every single row unless the user explicitly asks for all items.
If you do not know the answer based on authorized information, politely state so without hallucinating."""
        if context_str:
            base_prompt += f"""\n\nBase your answers on the following authorized knowledge and business records:\n{context_str}"""

    return base_prompt


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
            site = {
                "website_id": request.website_id,
                "tenant_id": "ten_default",
                "name": "Universal Assistant",
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

        # 4. Context Retrieval (RAG + Application Database)
        context_blocks: List[str] = []
        citations: List[SourceCitation] = []
        response_source = "general"

        # 4a. RAG Chunks (Website knowledge + User uploaded docs)
        relevant_chunks = rag_service.retrieve_relevant_chunks(
            tenant_id=tenant_id,
            website_id=request.website_id,
            query=request.message,
            conversation_id=active_conv_id,
            session_id=request.session_id,
            top_k=5,
        )
        seen_citations = set()
        if relevant_chunks:
            is_user_doc = any(c.get("is_user_document") for c in relevant_chunks)
            response_source = "user_document" if is_user_doc else "website_knowledge"
            rag_texts = []
            for c in relevant_chunks:
                source_label = f"Uploaded Document: {c['source_name']} (Chunk {c.get('chunk_index', 0) + 1})" if c.get("is_user_document") else f"Knowledge: {c['source_name']}"
                rag_texts.append(f"[{source_label}]\n{c['content']}")
                cit_type = "document" if c.get("is_user_document") else "website"
                cit_key = (cit_type, c["source_name"])
                if cit_key not in seen_citations:
                    seen_citations.add(cit_key)
                    citations.append(
                        SourceCitation(
                            source_type=cit_type,
                            title=c["source_name"],
                            snippet=c["content"][:150] + "...",
                        )
                    )
            context_blocks.append("--- RELEVANT KNOWLEDGE & UPLOADED DOCUMENT CONTENT ---\n" + "\n\n".join(rag_texts))

        # 4b. Application Database Search (e.g. Receipt Extractor DB or App DB)
        # If the user already uploaded a document and is asking about it, avoid polluting
        # the prompt with unrelated DB records unless explicitly requested.
        db_explicit_keywords = ["database", "stored receipt", "my receipts", "all receipts", "db"]
        should_query_db = (response_source != "user_document") or any(k in user_msg_lower for k in db_explicit_keywords)

        if should_query_db:
            app_data = app_mongo_adapter.query_application_data(
                website_id=request.website_id,
                user_query=request.message,
                user_id=verified_user_id,
            )
            if app_data and app_data.get("records"):
                if response_source == "general":
                    response_source = "app_database"
                db_summary = json.dumps(app_data["records"], indent=2, default=str)
                context_blocks.append(
                    f"--- APPLICATION DATABASE RECORDS ({app_data['collection']}) ---\n{db_summary}"
                )
                citations.append(
                    SourceCitation(
                        source_type="database",
                        title=f"Application DB ({app_data['collection']})",
                        snippet=f"Retrieved {app_data['record_count']} matching records.",
                    )
                )

        # 5. Load past context history (up to last 10 messages)
        history = get_conversation_history(active_conv_id, limit=10)
        history.append({"role": "user", "content": request.message})

        # 6. Build prompt & call MultiProvider AI Engine
        system_prompt = _build_system_prompt(bot_name, request.language, context_blocks)
        ai_res = ai_engine.generate_chat_response(
            messages=history,
            system_prompt=system_prompt,
            language=request.language,
        )

        bot_reply = ai_res.get("reply", "")

        # 7. Save message interaction into MongoDB
        msg_id = save_message_interaction(
            conversation_id=active_conv_id,
            website_id=request.website_id,
            tenant_id=tenant_id,
            user_message=request.message,
            bot_reply=bot_reply,
            language=request.language,
            source=response_source,
            meta={
                "provider": ai_res.get("provider"),
                "model": ai_res.get("model"),
                "latency": ai_res.get("latency"),
                "tokens": ai_res.get("tokens_used"),
                "citation_count": len(citations),
            },
        )

        return ChatMessageResponse(
            conversation_id=active_conv_id,
            message_id=msg_id,
            reply=bot_reply,
            language=request.language,
            source=response_source,
            citations=citations,
            escalate_to_human=False,
            created_at=get_ist_now_str(),
        )


chat_orchestrator = ChatOrchestrator()

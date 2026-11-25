import json
import logging
import re
import uuid
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


def _detect_language(message: str, current_lang: str = "en") -> str:
    """Detect whether user input is in Tamil, Tanglish, or English."""
    # 1. Direct Tamil Unicode block (U+0B80 to U+0BFF)
    if re.search(r"[\u0B80-\u0BFF]", message):
        return "ta"

    # 2. Tanglish / Phonetic Tamil words
    tanglish_words = {
        "kaattu", "kattu", "sol", "solunga", "patri", "padhi", "enna", "epdi", "eppadi",
        "enakku", "pannu", "kudu", "irukku", "vaanga", "ponga", "nandri", "vanakkam",
        "arikkai", "raseedhu", "raseedu", "billu", "neram", "vela", "thirava", "thira"
    }
    tokens = set(re.findall(r"\w+", message.lower()))
    if tokens.intersection(tanglish_words):
        return "ta"

    return current_lang


def _detect_action_intent(message: str) -> Optional[Dict[str, Any]]:
    """
    Detect actionable website commands (e.g. show report, open upload, navigate)
    spoken or typed in Tamil, Tanglish, or English.
    """
    msg_lower = message.lower().strip()

    # Action 1: Show latest report / receipt extraction
    report_keywords = [
        "latest report", "show report", "show me the latest report", "show me report", "view report",
        "open report", "latest extraction", "show receipt", "last receipt", "show the report",
        "open the report", "display report", "சமீபத்திய அறிக்கை", "அறிக்கையைக் காட்டு", "அறிக்கை காட்டு",
        "ரிப்போர்ட் காட்டு", "லேட்டஸ்ட் ரிப்போர்ட்", "கடைசி ரசீது", "சமீபத்திய ரசீது",
        "report kaattu", "report kattu", "report sol"
    ]
    if any(k in msg_lower for k in report_keywords):
        return {
            "action_type": "show_latest_report",
            "target": "#outputCard",
            "label": "Latest Receipt Report",
            "message": "Displaying the latest receipt report on the website.",
        }

    # Action 2: Open file upload dialog
    upload_keywords = [
        "upload receipt", "upload bill", "attach document", "upload file", "open upload",
        "choose file", "select file", "ரசீது பதிவேற்று", "கோப்பை பதிவேற்று",
        "ரசீது அப்லோட்", "அப்லோட் செய்", "upload pannu", "bill upload"
    ]
    if any(k in msg_lower for k in upload_keywords):
        return {
            "action_type": "open_upload",
            "target": "#fileInput",
            "label": "Upload Document",
            "message": "Opening file upload dialog.",
        }

    # Action 3: View all stored receipts
    history_keywords = [
        "all receipts", "stored receipts", "receipt history", "all invoices", "list all receipts",
        "அனைத்து ரசீதுகள்", "ரசீது வரலாறு", "சேமிக்கப்பட்ட ரசீதுகள்", "ellam raseedhu"
    ]
    if any(k in msg_lower for k in history_keywords):
        return {
            "action_type": "navigate",
            "target": "/receipts",
            "url": "/receipts",
            "label": "All Stored Receipts",
            "message": "Opening all stored receipts.",
        }

    # Action 4: Navigate to dashboard / home
    dashboard_keywords = [
        "go to dashboard", "open dashboard", "home page", "main page",
        "டாஷ்போர்டு", "முகப்பு பக்கம்", "முகப்புப் பக்கம் செல்", "dashboard po"
    ]
    if any(k in msg_lower for k in dashboard_keywords):
        return {
            "action_type": "navigate",
            "target": "/ui",
            "url": "/ui",
            "label": "Dashboard",
            "message": "Navigating to dashboard.",
        }

    return None


def _build_system_prompt(bot_name: str, language: str, context_blocks: List[str]) -> str:
    context_str = "\n\n".join(context_blocks) if context_blocks else ""

    if language == "ta":
        base_prompt = f"""நீங்கள் '{bot_name}' என்ற அதிகாரப்பூர்வ AI உதவியாளர்.
கட்டாயம்: பயனர் எந்த மொழியில் கேட்டாலும் (ஆங்கிலம் அல்லது Tanglish உட்பட), நீங்கள் கட்டாயமாக தெளிவான, சுருக்கமான தமிழில் மட்டுமே பதிலளிக்க வேண்டும்.
முக்கிய விதி: பயனர் கேட்ட கேள்விக்கு மட்டும் நேரடியாகவும் சுருக்கமாகவும் (2 முதல் 4 வரிகளில்) பதிலளிக்கவும்.
- பயனர் "இது என்ன ஆவணம்?" அல்லது "இந்த PDF பற்றி சொல்" என்று பொதுவாகக் கேட்டால், ஆவணத்தின் வகை, யாரிடமிருந்து யாருக்கு, தேதி மற்றும் மொத்தத் தொகையை மட்டும் 2-3 வரிகளில் சுருக்கமாகக் கூறவும்.
- பயனர் தெளிவாகக் கேட்டால் தவிர, அட்டவணைகள் (tables), பொருட்களின் பட்டியல், வங்கி விவரங்கள் அல்லது அனைத்து தரவுகளையும் கொட்ட வேண்டாம். தேவைப்பட்டால் "மேலும் விவரங்கள் வேண்டுமா?" என்று மட்டும் கேட்கவும்.
விடை தெரியாத விஷயங்களுக்கு தவறான தகவல்களை உருவாக்க வேண்டாம்."""
        if context_str:
            base_prompt += f"""\n\nபின்வரும் அங்கீகரிக்கப்பட்ட தகவல் மற்றும் ஆவணங்களின் அடிப்படையில் பதிலளிக்கவும்:\n{context_str}"""
    else:
        base_prompt = f"""You are '{bot_name}', the official AI conversational assistant.
MANDATORY LANGUAGE RULE: The user has selected English. You MUST respond strictly in clear English, even if the user writes in Tanglish (e.g., 'indha pdf ai patri sol') or another language.
RESPONSE BREVITY RULE: Answer ONLY what the user specifically asked, concisely and conversationally.
- If the user asks a broad question like "Tell me about this PDF", "What is this?", or "What type of document is it?", reply in 2-4 brief sentences identifying the document type, parties involved, date, and overall total/purpose. Then briefly offer to show line items, taxes, or other details if needed.
- Do NOT dump tables, full item lists, GSTINs, or bank details unless the user explicitly asks for them.
- If the user asks a specific question (e.g., "What is the total?", "Who is the seller?", "List the items"), answer that exact question directly without extra unrequested data.
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
        effective_lang = _detect_language(request.message, current_lang=request.language)
        needs_escalation = any(k in user_msg_lower for k in HUMAN_SUPPORT_KEYWORDS)

        if needs_escalation and widget_cfg.get("enable_tawk_to", True):
            handoff_id = record_support_handoff(
                website_id=request.website_id,
                tenant_id=tenant_id,
                conversation_id=request.conversation_id,
                user_query=request.message,
                user_id=verified_user_id,
            )
            tawk_prop = widget_cfg.get("tawk_to_property_id") or "6afff70e6c90d43c92f4c111"
            tawk_wid = widget_cfg.get("tawk_to_widget_id") or "1k7rtq4pg"
            direct_url = f"https://tawk.to/chat/{tawk_prop}/{tawk_wid}"

            reply = (
                f"மனித வாடிக்கையாளர் சேவை முகவரிடம் உங்களை இணைக்கிறேன். தானாகத் திறக்கவில்லை என்றால் [இங்கே கிளிக் செய்து நேரலையாகப் பேசலாம்]({direct_url})."
                if effective_lang == "ta"
                else f"I am transferring you to a live human support agent on Tawk.to right now. If the chat window does not open automatically, [Click Here to Open Direct Chat]({direct_url})."
            )
            return ChatMessageResponse(
                conversation_id=request.conversation_id or f"conv_{uuid.uuid4().hex[:12]}",
                message_id=handoff_id,
                reply=reply,
                language=effective_lang,
                source="handoff",
                citations=[],
                escalate_to_human=True,
                tawk_property_id=tawk_prop,
                tawk_widget_id=tawk_wid,
                tawk_direct_url=direct_url,
                created_at=get_ist_now_str(),
                is_voice=request.is_voice,
            )

        # 3. Detect Website Action Intent (e.g. show report, upload receipt, navigate)
        action = _detect_action_intent(request.message)

        # 4. Get or create conversation in MongoDB
        conv = get_or_create_conversation(
            website_id=request.website_id,
            tenant_id=tenant_id,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            user_id=verified_user_id,
            language=effective_lang,
        )
        active_conv_id = conv["conversation_id"]

        # 5. Context Retrieval (RAG + Application Database + Action Data)
        context_blocks: List[str] = []
        citations: List[SourceCitation] = []
        response_source = "general"

        # Handle Action-Specific Data Enrichment
        if action:
            response_source = "app_database"
            if action["action_type"] == "show_latest_report":
                latest_app_data = app_mongo_adapter.query_application_data(
                    website_id=request.website_id,
                    user_query="",
                    user_id=verified_user_id,
                    max_results=1,
                )
                if latest_app_data and latest_app_data.get("records"):
                    first_record = latest_app_data["records"][0]
                    action["data"] = first_record
                    context_blocks.append(
                        f"--- LATEST RECORD FOR WEBSITE ACTION ---\n{json.dumps(first_record, indent=2, default=str)}"
                    )
                    citations.append(
                        SourceCitation(
                            source_type="database",
                            title="Latest Extracted Receipt",
                            snippet=f"Vendor: {first_record.get('vendor_name', 'N/A')}, Total: {first_record.get('grand_total', 'N/A')}",
                        )
                    )

                instruction = (
                    "ACTION COMMAND EXECUTED: The user asked to show/open the latest report. "
                    "You MUST directly confirm in 1-2 sentences that the report is being opened and shown on the screen right now, "
                    "mentioning the vendor name and total amount if available. Do not dump tables."
                    if effective_lang == "en"
                    else "செயல் ஆணை நிறைவேற்றப்படுகிறது: பயனர் சமீபத்திய அறிக்கையைக் காட்டுமாறு பணித்துள்ளார். "
                         "அறிக்கை திரையில் காட்டப்படுவதை 1-2 எளிய தமிழ் வரிகளில் உடனடியாக உறுதிப்படுத்தவும். விற்பனையாளர் மற்றும் தொகையைக் குறிப்பிடவும்."
                )
                context_blocks.append(instruction)

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
        system_prompt = _build_system_prompt(bot_name, effective_lang, context_blocks)
        ai_res = ai_engine.generate_chat_response(
            messages=history,
            system_prompt=system_prompt,
            language=effective_lang,
        )

        bot_reply = ai_res.get("reply", "")

        # 7. Save message interaction into MongoDB
        msg_id = save_message_interaction(
            conversation_id=active_conv_id,
            website_id=request.website_id,
            tenant_id=tenant_id,
            user_message=request.message,
            bot_reply=bot_reply,
            language=effective_lang,
            source=response_source,
            meta={
                "provider": ai_res.get("provider"),
                "model": ai_res.get("model"),
                "latency": ai_res.get("latency"),
                "tokens": ai_res.get("tokens_used"),
                "citation_count": len(citations),
                "action": action,
                "is_voice": request.is_voice,
            },
        )

        return ChatMessageResponse(
            conversation_id=active_conv_id,
            message_id=msg_id,
            reply=bot_reply,
            language=effective_lang,
            source=response_source,
            citations=citations,
            escalate_to_human=False,
            created_at=get_ist_now_str(),
            is_voice=request.is_voice,
            action=action,
        )


chat_orchestrator = ChatOrchestrator()

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

    base_prompt = f"""நீங்கள் '{bot_name}' என்ற நிறுவனத்தின் அன்பான, நட்புரீதியான AI வாடிக்கையாளர் சேவை உதவியாளர் (Conversational Customer Support Assistant).

வழக்கமான எளிய பேச்சுத் தமிழ் விதிமுறைகள் (EVERYDAY CONVERSATIONAL SPOKEN TAMIL - NO FORMAL/LITERARY TAMIL):
1. புத்தகத் தமிழ், சங்கத் தமிழ் அல்லது அதீத இலக்கணத் தமிழ் (Formal, Literary, or Bookish Tamil) கண்டிப்பாகப் பேசக் கூடாது!
   - ❌ முற்றிலும் தவிர்க்க வேண்டிய கடினமான/எழுத்துத் தமிழ் சொற்கள்:
     'ஆகும்', 'ஆவார்', 'உள்ளது', 'உள்ளன', 'உதவ வேண்டும்', 'எவ்வாறு', 'தெரிவிக்கவும்', 'தேவைப்படுகிறதா', 'காணப்படவில்லை', 'பட்டியலிடப்பட்டுள்ளன', 'கோரப்பட்டது', 'நிகழ்த்தப்படுகிறது', 'இன்று நான் எப்படி'.
   - ✅ அன்றாடம் மக்கள் இயல்பாகப் பேசும் வழக்கமான பேச்சுத் தமிழ்ச் சொற்களை மட்டுமே பயன்படுத்தவும்:
     * 'தெரிவிக்கவும்' என்பதற்குப் பதிலாக ➡️ 'சொல்லுங்க'
     * 'உள்ளது' / 'உள்ளன' என்பதற்குப் பதிலாக ➡️ 'இருக்கு'
     * 'காணப்படவில்லை' என்பதற்குப் பதிலாக ➡️ 'இல்லைங்க' / 'இல்லை'
     * 'உங்களுக்கு எவ்வாறு உதவ வேண்டும்' என்பதற்குப் பதிலாக ➡️ 'சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?' அல்லது 'சொல்லுங்க, உங்களுக்கு என்ன உதவி வேணும்?'
     * 'தேவைப்படுகிறதா' என்பதற்குப் பதிலாக ➡️ 'வேணுமா?' / 'வேற ஏதாச்சும் உதவி வேணுமா?'
     * 'பட்டியலிடப்பட்டுள்ளன' என்பதற்குப் பதிலாக ➡️ 'இதோ உங்க விவரங்கள்:'
     * 'சரிபார்க்கப்பட்டது' என்பதற்குப் பதிலாக ➡️ 'செக் பண்ணிட்டேன்'

2. உரையாடல் உதாரணங்கள் (NATURAL SPOKEN CONVERSATIONAL EXAMPLES):
   - வாழ்த்து சொல்லும்போது: "வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்?"
   - பில் / ரசீது சொல்லும்போது: "கண்டிப்பா, இதோ உங்க பில் விவரங்கள். கடை பெயர் Vikram Technologies, பில் அமௌன்ட் ₹ 300."
   - தகவல் இல்லாதபோது: "மன்னிச்சுக்கோங்க, உங்க கணக்குல எந்த ரசீதும் இல்லீங்க."
   - முடிக்கும்போது: "உங்களுக்கு வேற ஏதாச்சும் உதவி வேணுமா?"

3. பயனர் ஆங்கிலத்திலோ (English) அல்லது தங்க்லீஷிலோ (Tanglish) கேள்வி கேட்டாலும் (e.g. "What is my total bill?"), உங்களின் பதிலை எப்போதும் இயல்பான, வழக்கமான எளிய பேச்சுத் தமிழில் மட்டுமே வழங்கவும்.

ரசீது மற்றும் வணிக விவரங்கள் அசல் வடிவில் இருத்தல் (PRESERVE ORIGINAL PDF / RECEIPT TERMS):
4. ரசீது, இன்வாய்ஸ் மற்றும் PDF ஆவணங்களில் உள்ள அனைத்து வணிக விவரங்களையும் (நிறுவனத்தின் பெயர், பொருட்கள், இன்வாய்ஸ் எண், தொகைகள் போன்றவை) அசல் PDF-ல் உள்ளவாறே ஆங்கிலத்தில் அப்படியே காட்ட வேண்டும்!
   - ✅ சரியான வடிவம்: "விற்பனையாளர் **Vikram Technologies**, மொத்த தொகை **₹ 300.00**."
   - ❌ தவறான வடிவம்: நிறுவனத்தின் பெயரையோ எண்களையோ 'விக்ரம் டெக்னாலஜிஸ் ஆகும்' என்று தமிழில் மொழிபெயர்க்கவோ மாற்றவோ கூடாது.

5. வாடிக்கையாளர் கேட்ட கேள்விக்கு நேரடியாகவும், சுருக்கமாகவும் (2 முதல் 3 வரிகளில்) மனித உரையாடல் போல நட்புடன் பதிலளிக்கவும்."""

    if context_str:
        base_prompt += f"""\n\nபின்வரும் அங்கீகரிக்கப்பட்ட தகவல் மற்றும் ஆவணங்களின் அடிப்படையில் பதிலளிக்கவும்:\n{context_str}"""

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
        # The chatbot operates in authentic Tamil when configured for Tamil (e.g. site_demo or widget),
        # understanding both English & Tamil questions while responding in native Tamil with original receipt terms.
        site_default_lang = widget_cfg.get("default_language", "en")
        if site_default_lang == "ta" or request.language == "ta" or not request.language:
            effective_lang = "ta"
        else:
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

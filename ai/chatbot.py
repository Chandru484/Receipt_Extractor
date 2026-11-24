import logging
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from ai.groq_client import get_groq_client, get_all_groq_api_keys, _sanitize_error, GroqExtractionError
from core.config import settings
from schemas.chat_schema import ChatMessage, ChatRequest, ChatResponse
from storage.mongo_client import get_mongo_client

logger = logging.getLogger(__name__)

CHATBOT_SYSTEM_PROMPT = """You are the official AI Assistant for the Receipt & Invoice Extractor API platform.
Your purpose is to help users, developers, and visitors understand the platform, how to use its API, its features, and how to troubleshoot their extractions.

PROJECT KNOWLEDGE BASE:
1. Core Capabilities:
   - High-accuracy receipt and invoice extraction combining local PaddleOCR 3.x and Groq LLM semantic reasoning.
   - Converts unstructured receipts/invoices into structured, validated JSON and clean formatted text receipts.
   - Extracts complete fields:
     * Seller / Vendor: Name, Full Address (including Address Line 1 and 2), GSTIN (15-character uppercase), State & State Code, Email, Phone / Landline, Mobile.
     * Buyer / Customer (Bill To): Name, Full Address (Line 1 and 2), GSTIN, State & State Code, Email, Mobile / Phone.
     * Document Details: Invoice/Bill No, Receipt No, Dates (standardized to DD-MM-YYYY format, e.g., '01-01-2023'), Payment Mode, Salesman.
     * Line Items: Sl No, Description, HSN/SAC code, Quantity, Unit of Measure (UOM), Unit Price, Rate (Incl. Tax), Total Price / Amount.
     * Taxes & Totals: CGST %, SGST %, IGST %, Subtotal, CGST amount, SGST amount, IGST amount, Rounding Off, Grand Total, Amount in Words.
     * Bank Details: Account Holder Name, Bank Name, Account Number, Branch, IFSC Code.
     * Additional Fields: PO Number, E-Way Bill Number, Delivery Note, Transport carrier, Contact Person.
   - Omits null or empty fields from the final JSON response for clean data delivery.

2. Supported File Formats:
   - PDFs: Single-page and multi-page PDFs (all pages are OCR'd and unified into a single extraction).
   - Images: JPG, JPEG, PNG, WebP, BMP.
   - Processing is 100% in-memory (zero temporary image files written to disk).
   - Configurable max upload size (default 10 MB).

3. API Endpoints & Usage:
   - Interactive Swagger UI: https://chandru484-receipt-extractor.hf.space/docs (or /docs locally).
   - POST /extract: Main endpoint. Accepts multipart/form-data with a 'file' parameter.
   - GET /health: Status check showing OCR engine, active Groq model, fallback status, and MongoDB connection.
   - GET /receipts: Paginated list of extracted receipts stored in the database (?limit=20&skip=0).
   - GET /receipts/{id}: Retrieve a specific stored receipt by its MongoDB ID.

4. Database & Duplicate Prevention:
   - Extractions are saved to MongoDB in the 'Receipt_Extraction' collection.
   - Duplicate Detection: Before saving, the system checks if an extraction with the same 'invoice_number' already exists. If found, duplicate saving is skipped ('is_duplicate: true') to prevent duplicate records.

5. Human Support & Escalation (Tawk.to):
   - If a visitor asks to speak to a human, asks to upload an image to ask custom questions, or wants to send a voice message, inform them warmly that they can connect with our live human team on Tawk.to.
   - In Tawk.to, visitors can directly attach images, record voice messages, and chat live with our support team.

RESPONSE GUIDELINES:
- Be concise, friendly, and helpful.
- Format code blocks and API paths using markdown (e.g. `/extract`, `POST`).
- If the user asks about uploading an image or voice message for queries, tell them to use the "Connect to Human Agent" button to chat with our team on Tawk.to.
"""

ESCALATION_PATTERNS = [
    (re.compile(r"\b(?:voice\s*message|voice\s*note|audio|mic|microphone)\b", re.IGNORECASE), "voice_message"),
    (re.compile(r"\b(?:human|agent|support\s*person|talk\s*to\s*(?:someone|a\s*person|human|agent)|customer\s*care|live\s*(?:support|chat))\b", re.IGNORECASE), "human_request"),
    (re.compile(r"\b(?:upload|attach|send)\s+(?:an?\s+)?(?:image|photo|picture|screenshot|file)\b", re.IGNORECASE), "image_upload"),
    (re.compile(r"\b(?:look\s*at|check|review)\s+my\s+(?:receipt|bill|invoice|image)\b", re.IGNORECASE), "image_upload"),
]


def ask_chatbot(request: ChatRequest) -> ChatResponse:
    """Process a chat request through Groq with project knowledge and escalation detection."""
    user_msg = request.message.strip()

    # Detect if user is asking for human agent, voice message, or image query
    is_escalation = False
    escalation_reason = None
    for pattern, reason in ESCALATION_PATTERNS:
        if pattern.search(user_msg):
            is_escalation = True
            escalation_reason = reason
            break

    # Assemble messages payload
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": CHATBOT_SYSTEM_PROMPT}
    ]

    # Include up to the last 6 history messages for conversation context
    if request.history:
        for hist_msg in request.history[-6:]:
            if hist_msg.role in ["user", "assistant"]:
                messages.append({"role": hist_msg.role, "content": hist_msg.content})

    # Add the current user message
    messages.append({"role": "user", "content": user_msg})

    reply_text = ""
    all_keys = get_all_groq_api_keys()
    chatbot_success = False

    for idx, key in enumerate(all_keys):
        chat_model = getattr(settings, "GROQ_CHAT_MODEL", None) or settings.GROQ_MODEL or "openai/gpt-oss-20b"
        model = chat_model if idx == 0 else (settings.GROQ_FALLBACK_MODEL or "openai/gpt-oss-20b")
        try:
            client = get_groq_client(api_key=key)
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.3,
                max_tokens=600
            )
            reply_text = response.choices[0].message.content.strip()
            if idx > 0:
                logger.info(f"Groq chatbot succeeded using fallback key #{idx + 1} ({model}).")
            chatbot_success = True
            break
        except Exception as exc:
            sanitized = _sanitize_error(str(exc))
            if idx < len(all_keys) - 1:
                logger.warning(f"Groq chatbot key #{idx + 1} failed ({sanitized}). Failing over to next key...")
            else:
                logger.error(f"All configured Groq keys failed for chatbot. Last error: {sanitized}")

    if not chatbot_success or not reply_text:
        reply_text = (
            "I am temporarily unable to reach the AI engine. "
            "You can test the extraction API directly via [Swagger Docs](/docs) "
            "or click below to connect with our human team on live chat!"
        )
        is_escalation = True
        escalation_reason = "service_unavailable"

    # If escalation detected, append a friendly guidance notice if not already mentioned
    if is_escalation and "tawk" not in reply_text.lower() and "live chat" not in reply_text.lower():
        reply_text += (
            "\n\n💬 *Would you like to connect with our human support team right now? "
            "Click the **Talk to Human / Attach Image** button below to open live chat, "
            "where you can attach images and send voice messages directly to our team!*"
        )

    # Save chat log to MongoDB asynchronously / safely if available
    _log_chat_interaction(user_msg, reply_text, is_escalation, request.session_id)

    return ChatResponse(
        reply=reply_text,
        escalate_to_tawk=is_escalation,
        escalation_reason=escalation_reason
    )


def _log_chat_interaction(user_msg: str, bot_reply: str, escalated: bool, session_id: Optional[str]):
    """Log chat interactions to MongoDB 'Chat_Logs' collection for monitoring."""
    try:
        client = get_mongo_client()
        if not client:
            return
        db = client[settings.MONGODB_DB_NAME]
        chat_collection = db["Chat_Logs"]
        IST = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(IST)
        chat_collection.insert_one({
            "timestamp": now_ist.strftime("%d-%m-%Y %H:%M:%S"),
            "date": now_ist.strftime("%d-%m-%Y"),
            "session_id": session_id or "anonymous",
            "user_message": user_msg,
            "bot_reply": bot_reply,
            "escalated_to_human": escalated
        })
    except Exception as exc:
        logger.debug(f"Failed to log chat interaction to MongoDB: {exc}")


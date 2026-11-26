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
    ensure_user_record,
)
from universal_chatbot.backend.app.services.rag_service import rag_service
from universal_chatbot.backend.app.application_adapters.mongodb_adapter import app_mongo_adapter

logger = logging.getLogger(__name__)

HUMAN_SUPPORT_KEYWORDS = [
    "human", "agent", "support", "talk to human", "customer care", "representative",
    "உதவியாளர்", "மனிதர்", "தொடர்பு", "வாடிக்கையாளர் சேவை"
]

GREETING_TOKENS = {
    "hi", "hello", "hey", "hola", "hai", "vanakkam", "வணக்கம்", "வணக்கங்க",
    "good", "morning", "afternoon", "evening", "day", "night",
    "how", "are", "you", "who", "what", "is", "your", "name", "can", "do",
    "epdi", "irukinga", "irukkeenga", "yar", "neenga", "yaaru", "unakku",
    "theriyum", "panra", "nandri", "thanks", "thank", "bye", "goodbye",
    "see", "welcome", "ok", "okay", "சரி", "சரிங்க", "ஹலோ", "ஹாய்"
}


def _is_pure_greeting_or_smalltalk(msg: str) -> bool:
    """Check if message is simply a greeting, small talk, or polite acknowledgement."""
    cleaned = re.sub(r"[^\w\s]", "", msg.strip().lower())
    if not cleaned:
        return True
    tokens = [t for t in cleaned.split() if t]
    if tokens and all(t in GREETING_TOKENS for t in tokens):
        return True
    return False


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


def _normalize_spoken_tamil_endings(text: str) -> str:
    """Normalize awkward bookish passive verb endings that artificially append 'ங்க' into natural spoken Tamil."""
    if not text:
        return text
    replacements = [
        (r"சேமிக்கப்பட்டுள்ளனங்க\b", "சேமிக்கப்பட்டிருக்கு"),
        (r"சேமிக்கப்பட்டு\s*உள்ளனங்க\b", "சேமிக்கப்பட்டிருக்கு"),
        (r"கிடைக்கின்றனங்க\b", "கிடைக்குது"),
        (r"கிடைக்கிறதுங்க\b", "கிடைக்குது"),
        (r"எடுக்கப்பட்டுள்ளனங்க\b", "எடுக்கப்பட்டிருக்கு"),
        (r"எடுக்கப்பட்டு\s*உள்ளனங்க\b", "எடுக்கப்பட்டிருக்கு"),
        (r"இருக்கின்றனங்க\b", "இருக்கு"),
        (r"உள்ளனங்க\b", "இருக்கு"),
        (r"வருகின்றனங்க\b", "வருது"),
        (r"காட்டப்பட்டுள்ளனங்க\b", "காட்டப்பட்டிருக்கு"),
        (r"குறிப்பிடப்பட்டுள்ளனங்க\b", "குறிப்பிடப்பட்டிருக்கு"),
        (r"பதிவேற்றப்பட்டுள்ளனங்க\b", "பதிவேற்றப்பட்டிருக்கு"),
        (r"செய்யப்பட்டுள்ளனங்க\b", "செய்யப்பட்டிருக்கு"),
        (r"தெரியவருகிறதுங்க\b", "தெரியவருது"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return text


def _build_system_prompt(bot_name: str, language: str, context_blocks: List[str]) -> str:
    context_str = "\n\n".join(context_blocks) if context_blocks else ""

    if language != "ta":
        base_prompt = f"""You are the polite, helpful, and professional AI customer support assistant for '{bot_name}'.

CORE GUIDELINES:
1. Always be polite, courteous, and professional.
2. Provide direct, clear, and concise answers (1 to 3 short sentences).
3. Do not repeatedly append robotic intros ('Hello! How can I help you today?') or closings ('Is there anything else I can help you with?') to every response. Answer the question directly.
4. When answering questions about receipts, expenses, bills, or store purchases:
   - Provide accurate figures directly from the verified database records or uploaded document content.
   - Mention the vendor / store name, date, invoice number, items, and total amount (using the '₹' currency symbol).
   - For total expenses or spending summaries, state the exact total amount and receipt count clearly.
5. If requested information is not in the database or document, politely state that the detail is not available.
6. Strictly ground your answers in the verified records and knowledge provided below."""
        if context_str:
            base_prompt += f"""\n\n--- VERIFIED KNOWLEDGE & DATABASE RECORDS ---\n{context_str}"""
        return base_prompt

    base_prompt = f"""நீங்கள் '{bot_name}' என்ற நிறுவனத்தின் அன்பான, பவ்யமான, மரியாதையான AI வாடிக்கையாளர் சேவை உதவியாளர் (Polite Customer Support Voice Assistant).

கண்ணியமான, மரியாதையான பேச்சுத் தமிழ் விதிமுறைகள் (POLITE & RESPECTFUL SPOKEN TAMIL - NO RUDE SLANG, NO BOOKISH TAMIL):
1. மரியாதை மற்றும் கண்ணியம் மிக முக்கியம் (STRICTLY FORBIDDEN SLANG):
   - ❌ 'இப்போடா', 'டா' (da), 'டி' (di), 'பா' (pa), 'மச்சி', 'சொல்லுடா', 'பண்ணுடா', 'பாருடா' போன்ற ஒருமை அல்லது மரியாதையற்ற கொச்சைச் சொற்களை ஒருபோதும் பயன்படுத்தக் கூடாது!
   - ✅ வாடிக்கையாளரிடம் நேரடியாக உரையாடும்போது 'ங்க' (nga) விகுதியுடன் மரியாதையாகப் பேச வேண்டும்:
     * 'இப்போடா' ❌ ➡️ 'இப்போதைக்கு' அல்லது 'தற்போது' ✅
     * 'சொல்லுடா' ❌ ➡️ 'சொல்லுங்க' ✅
     * 'பண்ணுடா' ❌ ➡️ 'பண்ணுங்க' ✅
     * 'இல்ல' ❌ ➡️ 'இல்லைங்க' / 'இல்லீங்க' ✅

2. இயல்பான பேச்சுத்தமிழ் மற்றும் வாக்கிய முடிவுகள் (NATURAL SPOKEN PECHU TAMIZH - NO AWKWARD "...னங்க" VERBS):
   - Respond in natural, polite spoken Tamil (மரியாதையான பேச்சுத்தமிழ்), not formal literary Tamil.
   - Use everyday polite words:
     * 'இருக்கு' instead of 'உள்ளது' / 'உள்ளன'
     * 'சொல்லுங்க' instead of 'கூறுங்கள்' / 'தெரிவிக்கவும்'
     * 'பண்ணலாம்' / 'பண்ணுங்க' instead of 'செய்யலாம்' / 'செய்யுங்கள்'
     * 'என்ன வேணும்' instead of 'என்ன வேண்டும்'
     * 'செக் பண்ணி சொல்றேன்' instead of 'சரிபார்க்கப்பட்டு தெரிவிக்கப்படும்'
     * 'அப்டேட் ஆயிடுச்சு' instead of 'புதுப்பிக்கப்பட்டது'
     * 'ப்ராப்ளம் இல்ல' instead of 'பிரச்சினை இல்லை'
     * 'இதோ உங்க விவரங்கள்' instead of 'பட்டியலிடப்பட்டுள்ளன'
   
   - ❌ செயற்கையான புத்தகத் தமிழ் + ங்க முடிவுகளைத் தவிர்க்கவும் (NO AWKWARD ENDINGS):
     * 'சேமிக்கப்பட்டுள்ளனங்க' ❌ ➡️ 'சேமிக்கப்பட்டிருக்கு' அல்லது 'சேவ் ஆகியிருக்கு' ✅
     * 'கிடைக்கின்றனங்க' ❌ ➡️ 'கிடைக்குது' அல்லது 'கிடைக்கிறது' என்று சொன்னால் போதும் ✅
     * 'எடுக்கப்பட்டுள்ளனங்க' ❌ ➡️ 'எடுக்கப்பட்டிருக்கு' ✅
     * 'இருக்கின்றனங்க' / 'உள்ளனங்க' ❌ ➡️ 'இருக்கு' ✅
     * 'வருகின்றனங்க' ❌ ➡️ 'வருது' அல்லது 'வருகிறது' ✅
     * 'காட்டப்பட்டுள்ளனங்க' ❌ ➡️ 'காட்டப்பட்டிருக்கு' ✅
   - விளக்கம்: 'ங்க' விகுதி மனிதர்களிடம் நேரடியாக விளிக்கும்போது மட்டுமே (சொல்லுங்க, பாருங்க, கேளுங்க, சரிங்க, இல்லைங்க, மன்னிச்சுக்கோங்க) வர வேண்டும். பொது விவரங்கள், அமைப்புகள் மற்றும் கணினிச் செயல்களைக் கூறும்போது வாக்கியத்தை இயல்பாக 'கிடைக்குது', 'சேமிக்கப்பட்டிருக்கு', 'இருக்கு' என்று முடித்தால் போதுமானது!
   - வாக்கியங்களை சுருக்கமாகவும் (1 அல்லது 2 சிறிய வரிகள்), இயல்பான உரையாடல் நடையிலும் அமையுங்கள்.
   - வாடிக்கையாளரிடம் ஒரு நல்ல கடையின் உதவியாளர் போல அன்பாகவும் மரியாதையாகவும் பேசுங்கள். பொதுவான வணிகச் சொற்களை இயல்பாகப் பயன்படுத்துங்கள் (இன்வாய்ஸ், பில், பேமென்ட், பேலன்ஸ், ஆர்டர், ஸ்டேட்டஸ்).

3. நேரடிப் பதில் மற்றும் தேவையற்ற வாக்கியங்களைத் தவிர்த்தல் (NO REPETITIVE GREETINGS OR CLOSINGS):
   - ❌ ஒவ்வொரு பதிலும் தொடங்கும் போது 'வணக்கம்! சொல்லுங்க, உங்களுக்கு நான் எப்படி உதவலாம்:', 'வணக்கம்! சொல்லுங்க...' போன்ற வாழ்த்துகளையோ, அல்லது பதிலின் முடிவில் 'உங்களுக்கு வேற ஏதாச்சும் உதவி வேணுமா?' போன்ற சலிப்பூட்டும் தொடர் வாக்கியங்களையோ மீண்டும் மீண்டும் சேர்க்கவே கூடாது!
   - ✅ வாடிக்கையாளர் கேட்ட கேள்விக்கான பதிலை மட்டும் நேரடியாக, கச்சிதமாகக் கூறுங்கள்.
   - வாடிக்கையாளர் முதலில் "வணக்கம்" அல்லது "hello" என்று வாழ்த்துக் கூறினால் மட்டுமே, "வணக்கம்! சொல்லுங்க, என்ன உதவி வேணும்?" என்று வாழ்த்துக் கூற வேண்டும்.
   - உரையாடல் உதாரணங்கள்:
     * பில் / ரசீது கேட்கும்போது: "கண்டிப்பா, இதோ உங்க பில் விவரங்கள். கடை பெயர் Vikram Technologies, பில் தொகை ₹ 300."
     * செலவு கேட்கும்போது: "இந்த மாசத்துல நீங்க மொத்தம் ₹ 218 செலவு பண்ணி இருக்கீங்க (2 ரசீதுகள்)."
     * கடை முகவரி கேட்கும்போது: "Vikram Technologies-ன் முகவரி: No:5, Bus Stand Complex, Mettur Road, Erode."
     * தகவல் இல்லாதபோது: "மன்னிச்சுக்கோங்க, அந்த விவரம் இதில் இல்லைங்க." (ஆவணம் இணைக்கப்பட்டிருந்தால், "மன்னிச்சுக்கோங்க, நீங்க பதிவேற்றிய ஆவணத்தில் அந்த விவரம் இல்லைங்க.")

4. பயனர் ஆங்கிலத்திலோ (English) அல்லது தங்க்லீஷிலோ (Tanglish) கேள்வி கேட்டாலும் (e.g. "kadayin address ai sollu"), உங்களின் பதிலை எப்போதும் மரியாதையான எளிய பேச்சுத் தமிழில் மட்டுமே வழங்கவும்.

ரசீது மற்றும் வணிக விவரங்கள் அசல் வடிவில் இருத்தல் (PRESERVE ORIGINAL PDF / RECEIPT TERMS):
5. ரசீது, இன்வாய்ஸ் மற்றும் PDF ஆவணங்களில் உள்ள அனைத்து வணிக விவரங்களையும் (நிறுவனத்தின் பெயர், முகவரி, பொருட்கள், இன்வாய்ஸ் எண், தொகைகள் போன்றவை) அசல் PDF-ல் உள்ளவாறே ஆங்கிலத்தில் அப்படியே காட்ட வேண்டும்!
   - ✅ சரியான வடிவம்: "கடை பெயர் **Vikram Technologies**, முகவரி **No:5, Bus Stand Complex, Mettur Road, Erode**, மொத்த தொகை **₹ 300.00**."
   - ❌ தவறான வடிவம்: நிறுவனத்தின் பெயரையோ முகவரியையோ தமிழில் மாற்றி குழப்பக் கூடாது.

6. வாடிக்கையாளர் கேட்ட கேள்விக்கு நேரடியாகவும், சுருக்கமாகவும் (2 முதல் 3 வரிகளில்) கனிவான குரலில் பதிலளிக்கவும்.

7. செலவு மற்றும் கணக்கு விவரங்களை மரியாதையான எளிய பேச்சுத் தமிழில் விளக்குதல் (EXPENSE & SPENDING ANALYTICS):
   - பயனர் மொத்த செலவு, குறிப்பிட்ட மாசத்து செலவு அல்லது குறிப்பிட்ட கடை செலவு பற்றிக் கேட்டால் (e.g. "இந்த மாசம் மொத்தம் எவ்வளவு செலவு பண்ணியிருக்கேன்?", "Vikram Technologies-க்கு எவ்வளவு செலவு?", "மொத்த செலவு எவ்வளவு?"):
   - எப்போதும் 'REAL-TIME EXPENSE & SPENDING ANALYTICS' பகுதியில் உள்ள துல்லியமான எண்களை மட்டுமே கொண்டு பதிலளிக்கவும்!
   - மரியாதையான எளிய பேச்சுத் தமிழில் 'ங்க' விகுதியுடன் கனிவாகப் பதிலளிக்கவும்:
     * இந்த மாசம் / குறிப்பிட்ட மாசம்: "இந்த மாசத்துல (அல்லது [மாசம்]-ல) நீங்க மொத்தம் ₹ [தொகை] செலவு பண்ணியிருக்கீங்க (மொத்தம் [எண்ணிக்கை] ரசீதுகள்)."
     * குறிப்பிட்ட கடை: "[கடை பெயர்]-க்கு மொத்தம் [எண்ணிக்கை] பில்கள்ல ₹ [தொகை] செலவு பண்ணியிருக்கீங்க."
     * மொத்த செலவு: "நீங்க இதுவரை மொத்தம் ₹ [தொகை] செலவு பண்ணியிருக்கீங்க (மொத்தம் [எண்ணிக்கை] ரசீதுகள்)."
     * அதிகபட்ச செலவு: "அதிகபட்சமா [கடை பெயர்]-ல மொத்தம் ₹ [தொகை] செலவு பண்ணியிருக்கீங்க."
   - கடை பெயர் மற்றும் தொகையை ஆங்கிலத்தில் (₹ [தொகை]) தெளிவாகக் குறிப்பிடவும்.
   - ஒருபோதும் கொச்சை slang (டா, டி, பா, மச்சி) அல்லது பழைய புத்தகத் தமிழ் (ஆகும், உள்ளது) பயன்படுத்தக் கூடாது!

8. மாதங்களின் முழுத் தமிழ்ப் பெயர்கள் (FULL TAMIL MONTH NAMES FOR VOICE SYNTHESIS):
   - மாதங்களின் பெயர்களை ஒருபோதும் ஆங்கிலத்தில் (Jan, Feb, Nov, November, Oct) என்று சுருக்கமாகவோ ஆங்கிலத்திலோ எழுதக் கூடாது!
   - எப்போதும் முழுமையான தமிழ்ப் பெயரையே எழுத வேண்டும்:
     * 'ஜனவரி', 'பிப்ரவரி', 'மார்ச்', 'ஏப்ரல்', 'மே', 'ஜூன்', 'ஜூலை', 'ஆகஸ்ட்', 'செப்டம்பர்', 'அக்டோபர்', 'நவம்பர்', 'டிசம்பர்'
   - உதாரணங்கள்:
     * "நவம்பர் மாசத்துல நீங்க மொத்தம் ₹ 218 செலவு பண்ணி இருக்கீங்க (2 ரசீதுகள்)."
     * "அக்டோபர் மாசத்துல 1 ரசீது, தொகை ₹ 500."
     * "ரசீது தேதி: 15 நவம்பர் 2024."
   - இப்படி முழுத் தமிழ்ப் பெயராக எழுதும்போது வாய்ஸ் அசிஸ்டண்ட் எந்தத் தடங்கலும் இன்றி மிகத் தெளிவாக உச்சரிக்கும்.

9. பயனர் பதிவேற்றிய ஆவணம் (USER ATTACHED / UPLOADED DOCUMENT):
   - பயனர் சாட்பாட்டில் ஏதேனும் PDF அல்லது ஆவணத்தைப் பதிவேற்றிவிட்டு, ஆவணப் பெயரைக் குறிப்பிடாமல் பொதுவான கேள்விகள் கேட்டாலும் (எ.கா. "வங்கி விவரங்கள் சொல்லு", "Bank details patri kooru", "மொத்தம் எவ்வளவு?", "பொருட்கள் என்னென்ன?", "இதை பத்தி சொல்லு"):
   - எப்போதும் இணைக்கப்பட்டுள்ள ஆவணத்தின் விவரங்களைக் கொண்டே பதிலளிக்க வேண்டும்! ஆவணப் பெயரை பயனர் மீண்டும் சொல்லவில்லை என்பதற்காக டேட்டாபேஸையோ கணக்கையோ பார்க்கக் கூடாது.
   - பயனர் கேட்கும் விவரம் (எ.கா. வங்கி விவரங்கள் / Bank details) அந்த ஆவணத்தில் இல்லை என்றால், "உங்க கணக்குல இல்லை" என்று ஒருபோதும் கூறக் கூடாது! மாறாக:
     "மன்னிச்சுக்கோங்க, நீங்க பதிவேற்றிய [ஆவணப் பெயர்]-ல் அந்த விவரம் (எ.கா. வங்கி விவரங்கள்) குறிப்பிடப்படவில்லைங்க. இதில் [கடை பெயர், பொருட்கள், மொத்தத் தொகை] மட்டுமே உள்ளது." என்று வெளிப்படையாகக் கூற வேண்டும்.
   - சரியான பேச்சுத்தமிழ் வடிவம்: 'பார்க்கி' ❌ ➡️ 'பார்த்து' ✅ (எ.கா. 'பார்த்துச் சொல்றேன்'), 'சொல்லுறேன்' ❌ ➡️ 'சொல்றேன்' ✅."""

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
                "name": "AI Assistant",
                "widget_config": {
                    "bot_name": "AI Assistant",
                    "enable_tawk_to": True,
                    "tawk_to_property_id": None,
                },
            }

        tenant_id = site.get("tenant_id", "ten_default")
        widget_cfg = site.get("widget_config", {})
        bot_name = widget_cfg.get("bot_name", "Assistant")

        # 2. Check for explicit human support request
        user_msg_lower = request.message.lower().strip()
        site_default_lang = widget_cfg.get("default_language", "en")

        # Default language is English ("en").
        # If user explicitly passed language ("en" or "ta"), honor it.
        # Otherwise auto-detect: if Tamil Unicode text is detected in user prompt, use "ta", else default to "en".
        if request.language == "ta":
            effective_lang = "ta"
        elif request.language == "en":
            effective_lang = "en"
        elif re.search(r"[\u0B80-\u0BFF]", request.message):
            effective_lang = "ta"
        else:
            effective_lang = site_default_lang or "en"

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

        # Resolve deterministic conversation_id if package_id + (user_id or admin_id) are provided
        target_uid = request.user_id or request.admin_id
        if target_uid:
            ensure_user_record(
                website_id=request.website_id,
                user_id=target_uid,
                role=request.role,
                package_id=request.package_id,
            )
        if request.package_id and target_uid and not request.conversation_id:
            clean_pkg = re.sub(r"[^\w\-]", "_", str(request.package_id).strip())
            clean_uid = re.sub(r"[^\w\-]", "_", str(target_uid).strip())
            request.conversation_id = f"conv_{clean_pkg}_{clean_uid}"

        # 4. Get or create conversation in MongoDB
        conv = get_or_create_conversation(
            website_id=request.website_id,
            tenant_id=tenant_id,
            conversation_id=request.conversation_id,
            session_id=request.session_id,
            user_id=verified_user_id,
            package_id=request.package_id,
            language=effective_lang,
        )
        active_conv_id = conv["conversation_id"]

        # 5. Context Retrieval (RAG + Application Database + Action Data)
        context_blocks: List[str] = []
        citations: List[SourceCitation] = []
        response_source = "general"
        executed_sql: Optional[str] = None

        # Inject dynamic package questions if supplied in request
        if request.package_questions:
            pkg_q_str = "\n".join([f"- {q}" for q in request.package_questions])
            context_blocks.append(
                f"--- ASSIGNED PACKAGE QUESTIONS FOR THIS USER/ROLE ---\n{pkg_q_str}\n"
                "The user may be selecting or asking one of these assigned package questions. Answer accurately and directly using relevant database records or document knowledge."
            )

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
            if is_user_doc:
                doc_name = relevant_chunks[0].get("source_name", "Uploaded Document")
                user_doc_instruction = (
                    f"--- USER ATTACHED / UPLOADED DOCUMENT: '{doc_name}' (CRITICAL) ---\n"
                    f"The user has uploaded and attached the document '{doc_name}' in this chat session.\n"
                    "The full text extracted across all pages of this document is provided in sequential reading order above.\n"
                    "RULES FOR ANSWERING:\n"
                    "1. ALWAYS answer based on this uploaded document, even if the user did NOT repeat the document's filename in their prompt!\n"
                    "2. MULTI-PAGE DOCUMENTS & COMPLETE PRODUCT COVERAGE:\n"
                    "   - In multi-page documents (Page 1, Page 2, etc.), items and text are spread across all pages.\n"
                    "   - Page 1 contains the top portion (Seller / Vendor name, invoice/order number, date, and early items like 1 to 37).\n"
                    "   - Subsequent pages contain the remaining items (e.g. 38 to 42), tax breakdown, totals, and bank details.\n"
                    "   - When the user asks for product/item details ('பொருட்கள் விவரம்', 'products', 'items', 'list'):\n"
                    "     DO NOT truncate to only the last page! Always examine all pages from item 1 to the final item.\n"
                    "     State the total item count (e.g. 'மொத்தம் 42 பொருட்கள்') and provide an accurate list or summary covering all pages.\n"
                    "3. ACCURACY & CONVERSATION HISTORY OVERRIDE:\n"
                    "   - ALWAYS prioritize the actual document content above over any incomplete previous assistant messages in the chat history.\n"
                    "   - Always check Page 1 / Chunk 1 for the Seller / Vendor name, invoice number, and date before claiming any information is missing.\n"
                    "4. If the user asks for a specific detail (such as bank details, IFSC, account number, discount, GST, PAN, etc.):\n"
                    "   - If it IS in the document text (such as Seller name on Page 1 or Bank details on Page 2), state it directly.\n"
                    f"   - If it is NOT in the document, explicitly state: 'மன்னிச்சுக்கோங்க, நீங்க பதிவேற்றிய \"{doc_name}\" ஆவணத்தில் அந்த விவரம் (எ.கா. வங்கி விவரங்கள்) எதுவும் குறிப்பிடப்படவில்லைங்க.' and briefly mention what IS in the document (vendor name, items count, grand total).\n"
                    "   - NEVER say 'உங்க கணக்குல இல்லை' (not in your account) when an uploaded document is attached!\n"
                    "5. Summarize key facts accurately: vendor name, invoice/quotation number, date, items, and grand total."
                )
                context_blocks.insert(0, user_doc_instruction)

        # 4b. Application Database Search (e.g. Receipt Extractor DB or App DB)
        # If the user is just saying hi/hello or smalltalk, do NOT trigger unnecessary database queries.
        # Also avoid polluting prompt with DB records if an uploaded document is the main topic.
        db_explicit_keywords = ["database", "stored receipt", "my receipts", "all receipts", "db"]
        is_smalltalk = _is_pure_greeting_or_smalltalk(request.message)
        should_query_db = (not is_smalltalk) and (
            (response_source != "user_document") or any(k in user_msg_lower for k in db_explicit_keywords)
        )

        if should_query_db:
            # Check for expense and spending analytics query
            is_expense = app_mongo_adapter.is_expense_query(request.message)
            if is_expense:
                expense_analytics = app_mongo_adapter.get_expense_analytics(
                    website_id=request.website_id,
                    user_query=request.message,
                    user_id=verified_user_id,
                )
                if expense_analytics:
                    if response_source == "general":
                        response_source = "app_database"
                    executed_sql = expense_analytics.get("generated_sql")
                    context_blocks.append(expense_analytics["summary_text"])
                    citations.append(
                        SourceCitation(
                            source_type="database",
                            title="Expense Analytics",
                            snippet=f"Analyzed {expense_analytics['receipt_count']} receipts. Total spent: ₹ {expense_analytics['total_spent']:,.2f}",
                        )
                    )

            app_data = app_mongo_adapter.query_application_data(
                website_id=request.website_id,
                user_query=request.message,
                user_id=verified_user_id,
            )
            if app_data and app_data.get("records"):
                if response_source == "general":
                    response_source = "app_database"
                if not executed_sql:
                    executed_sql = app_data.get("generated_sql")
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
        if request.is_voice:
            voice_prompt = (
                "குரல் பயன்முறை (ULTRA-FAST VOICE MODE ACTIVE): பயனர் நேரடியாகக் குரலில் பேசுகிறார். "
                "பதிலை அதிகபட்சம் 1 அல்லது 2 சிறிய வரிகளில் (30 வார்த்தைகளுக்குள்) கச்சிதமாகக் கூறவும். "
                "நீளமான பட்டியலையோ தேவையில்லாத விளக்கங்களையோ தவிர்த்து, நேரடியாகக் குரலில் பேச ஏதுவாகப் பதிலளிக்கவும்."
            )
            context_blocks.insert(0, voice_prompt)

        system_prompt = _build_system_prompt(bot_name, effective_lang, context_blocks)
        ai_res = ai_engine.generate_chat_response(
            messages=history,
            system_prompt=system_prompt,
            language=effective_lang,
        )

        bot_reply = ai_res.get("reply", "")

        # Strip repetitive robot greeting prefix if user query was not an explicit greeting
        greetings = ["வணக்கம்", "hi", "hello", "hey", "vanakkam", "வாழ்த்து", "good morning", "good evening"]
        if not any(g in user_msg_lower for g in greetings):
            bot_reply = re.sub(
                r"^\s*வணக்கம்!?\s*சொல்லுங்க,?\s*(உங்களுக்கு\s*நான்\s*எ[ப்இ]படி\s*உதவலாம்[:?.]?\s*)?",
                "",
                bot_reply,
                flags=re.IGNORECASE,
            )
            bot_reply = re.sub(
                r"^\s*வணக்கம்!?\s*",
                "",
                bot_reply,
                flags=re.IGNORECASE,
            ).strip()
            # If reply starts with colon, dash or extra punctuation, strip it
            bot_reply = re.sub(r"^[:,\- ]+", "", bot_reply).strip()
            if bot_reply and bot_reply[0].islower():
                bot_reply = bot_reply[0].upper() + bot_reply[1:]

        # Strip repetitive robot closing sentence if LLM appends it
        bot_reply = re.sub(
            r"\s*(?:உங்களுக்கு\s*)?(?:வேற|வேறு)\s*(?:ஏதாச்சும்|ஏதாவது|எதாவது)\s*உதவி\s*(?:வேண்டுமா|வேணுமா|தேவையா)[?.]?\s*$",
            "",
            bot_reply,
            flags=re.IGNORECASE,
        ).strip()

        # Clean typos and colloquial smoothing in bot reply
        bot_reply = re.sub(r"\bபார்க்கி\s*சொல்லுறேன்\b", "பார்த்துச் சொல்றேன்", bot_reply)
        bot_reply = re.sub(r"\bபார்க்கி\b", "பார்த்து", bot_reply)
        bot_reply = re.sub(r"\bசொல்லுறேன்\b", "சொல்றேன்", bot_reply)
        bot_reply = _normalize_spoken_tamil_endings(bot_reply)

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
                "sql_query": executed_sql,
                "package_id": request.package_id,
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
            package_id=request.package_id,
            sql_query=executed_sql,
            action=action,
        )


chat_orchestrator = ChatOrchestrator()

import io
import re
import logging
from typing import Optional, AsyncIterator, Dict, Tuple
import edge_tts

logger = logging.getLogger(__name__)

# Native Neural Voice Mappings
DEFAULT_VOICES = {
    "ta": "ta-IN-PallaviNeural",       # Fluent, native Tamil (India)
    "ta_male": "ta-IN-ValluvarNeural",  # Deep, natural Tamil male
    "en": "en-IN-NeerjaNeural",        # Clear Indian English
    "en_us": "en-US-JennyNeural",      # Standard US English
}

# English business/tech terms & Tamil loanwords -> Tamil script for native neural acoustic flow
TAMIL_PRONUNCIATION_MAP = {
    # English business & tech terms
    r"\binvoices?\b": "இன்வாய்ஸ்",
    r"\bpayments?\b": "பேமென்ட்",
    r"\bstocks?\b": "ஸ்டாக்",
    r"\bdiscounts?\b": "டிஸ்கவுண்ட்",
    r"\bbalances?\b": "பேலன்ஸ்",
    r"\bpending\b": "பெண்டிங்",
    r"\borders?\b": "ஆர்டர்",
    r"\bstatus\b": "ஸ்டேட்டஸ்",
    r"\btotal\b": "டோட்டல்",
    r"\bbills?\b": "பில்",
    r"\breports?\b": "ரிப்போர்ட்",
    r"\breceipts?\b": "ரசீது",
    r"\bdetails?\b": "விவரங்கள்",
    r"\bcustomers?\b": "கஸ்டமர்",
    r"\bvendors?\b": "வெண்டார்",
    r"\bdownloads?\b": "டவுன்லோடு",
    r"\bviews?\b": "வியூ",
    r"\bchecks?\b": "செக்",
    r"\bupdates?\b": "அப்டேட்",
    r"\bproblems?\b": "ப்ராப்ளம்",
    r"\bonline\b": "ஆன்லைன்",
    r"\boffline\b": "ஆஃப்லைன்",
    r"\bcables?\b": "கேபிள்",
    r"\bwarrant(y|ies)\b": "வாரண்டி",
    r"\bpower\b": "பவர்",
    r"\bcombo\b": "காம்போ",
    r"\bblack\b": "பிளாக்",
    r"\bwired\b": "வயர்",

    # Acronyms & Brands
    r"\bGSTIN\s*/\s*UIN\b": "ஜி எஸ் டி எண்",
    r"\bGSTIN\b": "ஜி எஸ் டி எண்",
    r"\bGST\b": "ஜி எஸ் டி",
    r"\bUPI\b": "யூ பி ஐ",
    r"\bQR\b": "க்யூ ஆர்",
    r"\bOTP\b": "ஓ டி பி",
    r"\bSMS\b": "எஸ் எம் எஸ்",
    r"\bAI\b": "ஏ.ஐ",
    r"\bPDF\b": "பி.டி.எஃப்",
    r"\bVikram\b": "விக்ரம்",
    r"\bTechnologies\b": "டெக்னாலஜிஸ்",
    r"\bSoftwares\b": "சாப்ட்வேர்ஸ்",
    r"\bSurya\b": "சூர்யா",
    r"\bZebronics\b": "ஜெப்ரானிக்ஸ்",
    r"\bAxis\s*Bank\b": "ஆக்சிஸ் பேங்க்",
    r"\bBank\b": "வங்கி",
    r"\bG\s*Pay\b": "ஜி பே",
    r"\bPhonePe\b": "போன்பே",

    # Cities (Erode -> ஈரோடு, never யாரோடு)
    r"\bErode\b": "ஈரோடு",
    r"\bEerodu\b": "ஈரோடு",
    r"\bCoimbatore\b": "கோயம்புத்தூர்",
    r"\bCovai\b": "கோவை",
    r"\bSalem\b": "சேலம்",
    r"\bChennai\b": "சென்னை",
    r"\bMadurai\b": "மதுரை",
    r"\bTirupur\b": "திருப்பூர்",
    r"\bTrichy\b": "திருச்சி",
    r"\bTamil\s*Nadu\b": "தமிழ்நாடு",
}

# Mapping of numeric months (01-12) to full Tamil speech
MONTH_NUM_TO_TAMIL = {
    "01": "ஜனவரி", "1": "ஜனவரி",
    "02": "பிப்ரவரி", "2": "பிப்ரவரி",
    "03": "மார்ச்", "3": "மார்ச்",
    "04": "ஏப்ரல்", "4": "ஏப்ரல்",
    "05": "மே", "5": "மே",
    "06": "ஜூன்", "6": "ஜூன்",
    "07": "ஜூலை", "7": "ஜூலை",
    "08": "ஆகஸ்ட்", "8": "ஆகஸ்ட்",
    "09": "செப்டம்பர்", "9": "செப்டம்பர்",
    "10": "அக்டோபர்",
    "11": "நவம்பர்",
    "12": "டிசம்பர்",
}

# Comprehensive Month replacements for Tamil speech
# Handles attached suffixes like -ல, -ல், -இல், full month names, 3-letter abbreviations, and dates
MONTH_SPEECH_REPLACEMENTS = [
    # Attached colloquial Tamil locative suffixes: e.g. November-ல, Nov-ல, Novemberல, Novல -> நவம்பர்ல
    (r"\bJan(?:uary)?[- ]?(?:ல|ல்|இல்)\b", "ஜனவரில"),
    (r"\bFeb(?:ruary)?[- ]?(?:ல|ல்|இல்)\b", "பிப்ரவரில"),
    (r"\bMar(?:ch)?[- ]?(?:ல|ல்|இல்)\b", "மார்ச்ல"),
    (r"\bApr(?:il)?[- ]?(?:ல|ல்|இல்)\b", "ஏப்ரல்ல"),
    (r"\bMay[- ]?(?:ல|ல்|இல்)\b", "மே மாசத்துல"),
    (r"\bJun(?:e)?[- ]?(?:ல|ல்|இல்)\b", "ஜூன்ல"),
    (r"\bJul(?:y)?[- ]?(?:ல|ல்|இல்)\b", "ஜூலைல"),
    (r"\bAug(?:ust)?[- ]?(?:ல|ல்|இல்)\b", "ஆகஸ்ட்ல"),
    (r"\bSep(?:t(?:ember)?)?[- ]?(?:ல|ல்|இல்)\b", "செப்டம்பர்ல"),
    (r"\bOct(?:ober)?[- ]?(?:ல|ல்|இல்)\b", "அக்டோபர்ல"),
    (r"\bNov(?:ember)?[- ]?(?:ல|ல்|இல்)\b", "நவம்பர்ல"),
    (r"\bDec(?:ember)?[- ]?(?:ல|ல்|இல்)\b", "டிசம்பர்ல"),

    # Attached Tamil dative suffixes: e.g. November-க்கு, Nov-க்கு -> நவம்பருக்கு
    (r"\bJan(?:uary)?[- ]?க்கு\b", "ஜனவரிக்கு"),
    (r"\bFeb(?:ruary)?[- ]?க்கு\b", "பிப்ரவரிக்கு"),
    (r"\bMar(?:ch)?[- ]?க்கு\b", "மார்ச்சுக்கு"),
    (r"\bApr(?:il)?[- ]?க்கு\b", "ஏப்ரலுக்கு"),
    (r"\bMay[- ]?க்கு\b", "மே மாதத்துக்கு"),
    (r"\bJun(?:e)?[- ]?க்கு\b", "ஜூனுக்கு"),
    (r"\bJul(?:y)?[- ]?க்கு\b", "ஜூலைக்கு"),
    (r"\bAug(?:ust)?[- ]?க்கு\b", "ஆகஸ்ட்டுக்கு"),
    (r"\bSep(?:t(?:ember)?)?[- ]?க்கு\b", "செப்டம்பருக்கு"),
    (r"\bOct(?:ober)?[- ]?க்கு\b", "அக்டோபருக்கு"),
    (r"\bNov(?:ember)?[- ]?க்கு\b", "நவம்பருக்கு"),
    (r"\bDec(?:ember)?[- ]?க்கு\b", "டிசம்பருக்கு"),

    # Dates with day + month + year: e.g. 15-Nov-2024, 15/Nov/2024, 15 Nov 2024, 15th November 2024
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Jan(?:uary)?[-\s/]+(\d{2,4})\b", r"\1 ஜனவரி \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Feb(?:ruary)?[-\s/]+(\d{2,4})\b", r"\1 பிப்ரவரி \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Mar(?:ch)?[-\s/]+(\d{2,4})\b", r"\1 மார்ச் \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Apr(?:il)?[-\s/]+(\d{2,4})\b", r"\1 ஏப்ரல் \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+May[-\s/]+(\d{2,4})\b", r"\1 மே \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Jun(?:e)?[-\s/]+(\d{2,4})\b", r"\1 ஜூன் \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Jul(?:y)?[-\s/]+(\d{2,4})\b", r"\1 ஜூலை \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Aug(?:ust)?[-\s/]+(\d{2,4})\b", r"\1 ஆகஸ்ட் \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Sep(?:t(?:ember)?)?[-\s/]+(\d{2,4})\b", r"\1 செப்டம்பர் \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Oct(?:ober)?[-\s/]+(\d{2,4})\b", r"\1 அக்டோபர் \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Nov(?:ember)?[-\s/]+(\d{2,4})\b", r"\1 நவம்பர் \2"),
    (r"\b(\d{1,2})(?:st|nd|rd|th)?[-\s/]+Dec(?:ember)?[-\s/]+(\d{2,4})\b", r"\1 டிசம்பர் \2"),

    # Month + Day format: e.g. Nov 15, 2024 or November 15
    (r"\bJan(?:uary)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 ஜனவரி"),
    (r"\bFeb(?:ruary)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 பிப்ரவரி"),
    (r"\bMar(?:ch)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 மார்ச்"),
    (r"\bApr(?:il)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 ஏப்ரல்"),
    (r"\bMay\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 மே"),
    (r"\bJun(?:e)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 ஜூன்"),
    (r"\bJul(?:y)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 ஜூலை"),
    (r"\bAug(?:ust)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 ஆகஸ்ட்"),
    (r"\bSep(?:t(?:ember)?)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 செப்டம்பர்"),
    (r"\bOct(?:ober)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 அக்டோபர்"),
    (r"\bNov(?:ember)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 நவம்பர்"),
    (r"\bDec(?:ember)?\s+(\d{1,2})(?:st|nd|rd|th)?\b", r"\1 டிசம்பர்"),

    # Standalone full month names and abbreviations
    (r"\bJan(?:uary)?\.?\b", "ஜனவரி"),
    (r"\bFeb(?:ruary)?\.?\b", "பிப்ரவரி"),
    (r"\bMar(?:ch)?\.?\b", "மார்ச்"),
    (r"\bApr(?:il)?\.?\b", "ஏப்ரல்"),
    (r"\bMay\.?\b", "மே"),
    (r"\bJun(?:e)?\.?\b", "ஜூன்"),
    (r"\bJul(?:y)?\.?\b", "ஜூலை"),
    (r"\bAug(?:ust)?\.?\b", "ஆகஸ்ட்"),
    (r"\bSep(?:t(?:ember)?)?\.?\b", "செப்டம்பர்"),
    (r"\bOct(?:ober)?\.?\b", "அக்டோபர்"),
    (r"\bNov(?:ember)?\.?\b", "நவம்பர்"),
    (r"\bDec(?:ember)?\.?\b", "டிசம்பர்"),
]


def sanitize_text_for_speech(text: str, language: str = "en") -> str:
    """
    Clean markdown, table borders, URLs, and expand technical symbols
    into natural spoken Tamil or English.
    """
    if not text:
        return ""

    # Normalize unicode spaces and non-breaking spaces
    text = re.sub(r"[\u00A0\u1680\u2000-\u200B\u202F\u205F\u3000]", " ", text)

    # Remove URLs
    cleaned = re.sub(r"https?://\S+", "", text)

    # Remove code blocks
    cleaned = re.sub(r"```[\s\S]*?```", "", cleaned)
    cleaned = re.sub(r"`[^`]*`", "", cleaned)

    # Remove markdown table formatting and pipes
    lines = cleaned.splitlines()
    speech_lines = []
    for line in lines:
        line_str = line.strip()
        # Skip markdown table divider lines like |---|---|
        if re.match(r"^\|?[\s\-:|]+\|?$", line_str):
            continue
        # If it's a table row, strip outer pipes and replace inner pipes with commas
        if line_str.startswith("|") and line_str.endswith("|"):
            cells = [c.strip() for c in line_str[1:-1].split("|") if c.strip()]
            line_str = ", ".join(cells)
        speech_lines.append(line_str)

    cleaned = " ".join(speech_lines)

    # Remove markdown header tokens, bold, italic, bullets
    cleaned = re.sub(r"[#*_~]", "", cleaned)
    cleaned = re.sub(r"^\s*[-+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+\.\s+", "", cleaned, flags=re.MULTILINE)

    is_tamil = (
        language.lower().startswith("ta")
        or language.lower() in ("tamil", "ta-in")
        or bool(re.search(r"[\u0B80-\u0BFF]", cleaned))
    )

    if is_tamil:
        # 0. Space out 15-character Indian GST numbers first so neural voice articulates each character clearly
        cleaned = re.sub(
            r"\b([0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1})\b",
            lambda m: " ".join(list(m.group(1))),
            cleaned
        )

        # 1. Split CamelCase & concatenated words/numbers like Bill102 -> Bill 102
        cleaned = re.sub(r"([a-zA-Z]+)(\d+)", r"\1 \2", cleaned)
        cleaned = re.sub(r"(\d+)([a-zA-Z]+)", r"\1 \2", cleaned)

        # 2. Remove commas inside numbers so Edge TTS speaks continuous Tamil numerals ("ஆறு லட்சத்து இருபதாயிரம்")
        # instead of saying "கமா" or pausing awkwardly
        cleaned = re.sub(r"(?<=\d),(?=\d)", "", cleaned)

        # 3. Strip decimal cents/paise from currency amounts so TTS speaks clean numbers (e.g. ₹ 254 instead of robotic 'புள்ளி இருபத்து நான்கு')
        cleaned = re.sub(r"₹\s*([\d,]+)\.\d+", r"₹ \1", cleaned)
        cleaned = re.sub(r"Rs\.?\s*([\d,]+)\.\d+", r"Rs \1", cleaned)
        cleaned = re.sub(r"([\d,]+)\.00\b", r"\1", cleaned)

        # 4. Remove repetitive closing questions
        cleaned = re.sub(r"(?:உங்களுக்கு\s*)?(?:வேற|வேறு)\s*(?:ஏதாச்சும்|ஏதாவது|எதாவது)\s*உதவி\s*(?:வேண்டுமா|வேணுமா|தேவையா)[?.]?", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bபார்க்கி\s*சொல்லுறேன்\b", "பார்த்துச் சொல்றேன்", cleaned)
        cleaned = re.sub(r"\bபார்க்கி\b", "பார்த்து", cleaned)
        cleaned = re.sub(r"\bசொல்லுறேன்\b", "சொல்றேன்", cleaned)

        # 5. Convert numeric dates to full Tamil month speech: e.g. 15/11/2024 or 2024-11-15 -> 15 நவம்பர் 2024
        cleaned = re.sub(
            r"\b([0-3]?\d)[-/](0[1-9]|1[0-2])[-/](20\d\d|19\d\d)\b",
            lambda m: f"{m.group(1)} {MONTH_NUM_TO_TAMIL[m.group(2)]} {m.group(3)}",
            cleaned
        )
        cleaned = re.sub(
            r"\b(20\d\d|19\d\d)[-/](0[1-9]|1[0-2])[-/]([0-3]?\d)\b",
            lambda m: f"{m.group(3)} {MONTH_NUM_TO_TAMIL[m.group(2)]} {m.group(1)}",
            cleaned
        )

        # 6. Apply comprehensive month speech replacements (Nov, November, Nov-ல, Nov 2024, etc.)
        for pat, repl in MONTH_SPEECH_REPLACEMENTS:
            cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)

        # 7. Section headings (Buyer, Bill to, Seller, Company, Address)
        cleaned = re.sub(r"\bBuyer\s*\(\s*Bill\s*to\s*\)\s*details\b", "வாங்குபவர் விவரங்கள்:", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bBuyer\s*details\b", "வாங்குபவர் விவரங்கள்:", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bSeller\s*details\b", "விற்பனையாளர் விவரங்கள்:", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bCompany\s*:", "நிறுவனம்:", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bAddress\s*:", "முகவரி:", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bGSTIN\s*/\s*UIN\s*:", "ஜி.எஸ்.டி எண்:", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bGSTIN\s*:", "ஜி.எஸ்.டி எண்:", cleaned, flags=re.IGNORECASE)

        # Apply comprehensive Tamil phonetic pronunciation map
        for pat, repl in TAMIL_PRONUNCIATION_MAP.items():
            cleaned = re.sub(pat, repl, cleaned, flags=re.IGNORECASE)

        # 6. Remove rude/disrespectful singular slang if LLM ever outputs it
        cleaned = re.sub(r"\bஇப்போடா\b", "இப்போதைக்கு", cleaned)
        cleaned = re.sub(r"\bஇப்பொடா\b", "இப்போதைக்கு", cleaned)
        cleaned = re.sub(r"\bசொல்லுடா\b", "சொல்லுங்க", cleaned)
        cleaned = re.sub(r"\bபண்ணுடா\b", "பண்ணுங்க", cleaned)
        cleaned = re.sub(r"\bபாருடா\b", "பாருங்க", cleaned)
        cleaned = re.sub(r"\bடா\b", "", cleaned)

        # 7. Smooth out bookish/formal words into natural polite conversational spoken Tamil
        cleaned = re.sub(r"\bஆகும்\b", "", cleaned)
        cleaned = re.sub(r"\bஆவார்\b", "", cleaned)
        cleaned = re.sub(r"\bஉள்ளது\b", "இருக்கு", cleaned)
        cleaned = re.sub(r"\bஉள்ளன\b", "இருக்கு", cleaned)
        cleaned = re.sub(r"\bகாணப்படவில்லை\b", "இல்லைங்க", cleaned)
        cleaned = re.sub(r"\bதேவைப்படுகிறதா\b", "வேணுமா", cleaned)
        cleaned = re.sub(r"\bதெரிவிக்கவும்\b", "சொல்லுங்க", cleaned)
        cleaned = re.sub(r"\bபட்டியலிடப்பட்டுள்ளன\b", "இதோ இருக்கு", cleaned)

        # 8. Separate compound/agglutinated spoken Tamil verbs for crisp neural enunciation
        cleaned = re.sub(r"\bபண்ணியிருக்கீங்க\b", "பண்ணி இருக்கீங்க", cleaned)
        cleaned = re.sub(r"\bபண்ணியிருக்கேன்\b", "பண்ணி இருக்கேன்", cleaned)
        cleaned = re.sub(r"\bபண்ணியிருக்காங்க\b", "பண்ணி இருக்காங்க", cleaned)
        cleaned = re.sub(r"\bசெலவாகியிருக்குங்க\b", "செலவாகி இருக்குங்க", cleaned)
        cleaned = re.sub(r"\bசெலவாகியிருக்கு\b", "செலவாகி இருக்கு", cleaned)
        cleaned = re.sub(r"\bபில்கள்ல\b", "பில்களில்", cleaned)
        cleaned = re.sub(r"\bஇப்போதைக்கு\b", "தற்போது", cleaned)

        # 9. Address details & pincodes
        cleaned = re.sub(r"\bNo\s*[:.]?\s*(\d+)", r"எண் \1", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bBus\s*Stand\b", "பஸ் ஸ்டாண்ட்", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bComplex\b", "காம்ப்ளக்ஸ்", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bRoad\b", "ரோடு", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bStreet\b", "தெரு", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bAgency\b", "ஏஜென்சி", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bElectricals\b", "எலக்ட்ரிக்கல்ஸ்", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\bTekis\b", "டெக்கிஸ்", cleaned, flags=re.IGNORECASE)
        
        # Pincodes with standard or unicode non-breaking hyphens (e.g. Erode‑638001 -> ஈரோடு பின்கோடு 638001)
        cleaned = re.sub(r"[-\u2010-\u2015\u2212]\s*(\d{6})\b", r" பின்கோடு \1", cleaned)

        # 10. Expand common symbols to spoken conversational Tamil
        cleaned = cleaned.replace("₹", " ரூபாய் ")
        cleaned = cleaned.replace("Rs.", " ரூபாய் ")
        cleaned = cleaned.replace("Rs", " ரூபாய் ")
        cleaned = cleaned.replace("%", " சதவீதம் ")
        cleaned = cleaned.replace("&", " மற்றும் ")
        cleaned = cleaned.replace("GST", " ஜி.எஸ்.டி ")
        cleaned = cleaned.replace("GSTIN", " ஜி.எஸ்.டி எண் ")
        cleaned = cleaned.replace("Invoice No", " இன்வாய்ஸ் எண் ")
        cleaned = cleaned.replace("Bill No", " பில் எண் ")
        cleaned = cleaned.replace("Date:", " தேதி ")
        cleaned = cleaned.replace("Total", " மொத்தத் தொகை ")
        cleaned = cleaned.replace("Nos", " எண்ணிக்கை ")
        cleaned = cleaned.replace("MTR", " மீட்டர் ")
        cleaned = cleaned.replace("Qty", " அளவு ")
        cleaned = cleaned.replace("kg", " கிலோ ")
        cleaned = cleaned.replace("KG", " கிலோ ")
        cleaned = cleaned.replace("g ", " கிராம் ")

        # 11. Punctuation smoothing for natural speech cadence
        cleaned = cleaned.replace(":", " ")
        cleaned = cleaned.replace(";", " ")
        cleaned = cleaned.replace("/", " அல்லது ")
        cleaned = cleaned.replace("(", ", ")
        cleaned = cleaned.replace(")", ", ")
    else:
        # Expand for English
        cleaned = cleaned.replace("₹", " Rupees ")
        cleaned = cleaned.replace("%", " percent ")
        cleaned = cleaned.replace("&", " and ")

    # Collapse multiple whitespaces
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # Limit to reasonable speech length if text is huge (first ~800 chars for speech)
    if len(cleaned) > 1200:
        sentences = re.split(r"(?<=[.!?।])\s+", cleaned)
        truncated = []
        curr_len = 0
        for s in sentences:
            if curr_len + len(s) > 1000:
                break
            truncated.append(s)
            curr_len += len(s)
        if truncated:
            cleaned = " ".join(truncated)

    return cleaned


# In-memory LRU cache for ultra-fast instantaneous voice playback (<10ms)
_TTS_CACHE: Dict[Tuple[str, str, str], bytes] = {}
_MAX_CACHE_ENTRIES = 128


async def prewarm_tts_cache(
    text: str,
    language: str = "en",
    voice: Optional[str] = None
) -> None:
    """
    Pre-synthesize speech in background immediately after chat response generation.
    Populates in-memory LRU cache so when browser requests /api/v1/voice/tts,
    the audio is served from RAM with zero synthesis delay.
    """
    clean_text = sanitize_text_for_speech(text, language=language)
    if not clean_text:
        return

    selected_voice = voice or DEFAULT_VOICES.get(language, DEFAULT_VOICES["en"])
    cache_key = (clean_text, language, selected_voice)
    if cache_key in _TTS_CACHE:
        return

    try:
        rate_param = "+10%" if "Pallavi" in selected_voice else "+4%"
        pitch_param = "+2Hz" if "Pallavi" in selected_voice else "-2Hz"
        communicate = edge_tts.Communicate(clean_text, selected_voice, rate=rate_param, pitch=pitch_param)
        collected = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                collected.extend(chunk["data"])

        if len(collected) > 0 and len(collected) < 1_500_000:
            if len(_TTS_CACHE) >= _MAX_CACHE_ENTRIES:
                first_key = next(iter(_TTS_CACHE))
                _TTS_CACHE.pop(first_key, None)
            _TTS_CACHE[cache_key] = bytes(collected)
    except Exception as exc:
        logger.debug(f"prewarm_tts_cache notice: {exc}")


async def generate_speech_stream(
    text: str,
    language: str = "en",
    voice: Optional[str] = None
) -> AsyncIterator[bytes]:
    """
    Generate native neural audio stream (MP3) for Tamil or English.
    Utilizes an in-memory memory cache for repeated greetings and common phrases
    to eliminate round-trip latency.
    """
    clean_text = sanitize_text_for_speech(text, language=language)
    if not clean_text:
        return

    # Select native voice
    selected_voice = voice
    if not selected_voice:
        selected_voice = DEFAULT_VOICES.get(language, DEFAULT_VOICES["en"])

    cache_key = (clean_text, language, selected_voice)
    if cache_key in _TTS_CACHE:
        # Cache hit: instantaneous response directly from RAM
        yield _TTS_CACHE[cache_key]
        return

    # Friendly, casual shop-assistant prosody: +10% rate tightens natural silence between commas; +2Hz lifts brightness
    rate_param = "+10%" if "Pallavi" in selected_voice else "+4%"
    pitch_param = "+2Hz" if "Pallavi" in selected_voice else "-2Hz"
    communicate = edge_tts.Communicate(clean_text, selected_voice, rate=rate_param, pitch=pitch_param)
    
    collected_chunks = bytearray()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunk_data = chunk["data"]
            collected_chunks.extend(chunk_data)
            yield chunk_data

    # Store in memory cache if within reasonable entry size (< 1MB)
    if len(collected_chunks) > 0 and len(collected_chunks) < 1_000_000:
        if len(_TTS_CACHE) >= _MAX_CACHE_ENTRIES:
            # Pop oldest entry (FIFO)
            first_key = next(iter(_TTS_CACHE))
            _TTS_CACHE.pop(first_key, None)
        _TTS_CACHE[cache_key] = bytes(collected_chunks)

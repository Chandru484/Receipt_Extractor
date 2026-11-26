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


def sanitize_text_for_speech(text: str, language: str = "en") -> str:
    """
    Clean markdown, table borders, URLs, and expand technical symbols
    into natural spoken Tamil or English.
    """
    if not text:
        return ""

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

    if language == "ta":
        # Strip decimal cents/paise from currency amounts so TTS speaks clean numbers (e.g. ₹ 254 instead of robotic 'புள்ளி இருபத்து நான்கு')
        cleaned = re.sub(r"₹\s*([\d,]+)\.\d+", r"₹ \1", cleaned)
        cleaned = re.sub(r"Rs\.?\s*([\d,]+)\.\d+", r"Rs \1", cleaned)
        cleaned = re.sub(r"([\d,]+)\.00\b", r"\1", cleaned)

        # Remove rude/disrespectful singular slang if LLM ever outputs it
        cleaned = re.sub(r"\bஇப்போடா\b", "இப்போதைக்கு", cleaned)
        cleaned = re.sub(r"\bஇப்பொடா\b", "இப்போதைக்கு", cleaned)
        cleaned = re.sub(r"\bசொல்லுடா\b", "சொல்லுங்க", cleaned)
        cleaned = re.sub(r"\bபண்ணுடா\b", "பண்ணுங்க", cleaned)
        cleaned = re.sub(r"\bபாருடா\b", "பாருங்க", cleaned)
        cleaned = re.sub(r"\bடா\b", "", cleaned)

        # Smooth out bookish/formal words into natural polite conversational spoken Tamil
        cleaned = re.sub(r"\bஆகும்\b", "", cleaned)
        cleaned = re.sub(r"\bஆவார்\b", "", cleaned)
        cleaned = re.sub(r"\bஉள்ளது\b", "இருக்கு", cleaned)
        cleaned = re.sub(r"\bஉள்ளன\b", "இருக்கு", cleaned)
        cleaned = re.sub(r"\bகாணப்படவில்லை\b", "இல்லைங்க", cleaned)
        cleaned = re.sub(r"\bதேவைப்படுகிறதா\b", "வேணுமா", cleaned)
        cleaned = re.sub(r"\bதெரிவிக்கவும்\b", "சொல்லுங்க", cleaned)
        cleaned = re.sub(r"\bபட்டியலிடப்பட்டுள்ளன\b", "இதோ இருக்கு", cleaned)

        # Expand common symbols to spoken conversational Tamil
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

    # Natural conversational pacing (+4% rate removes robotic drag for Tamil neural voice)
    rate_param = "+4%" if language == "ta" else "+0%"
    communicate = edge_tts.Communicate(clean_text, selected_voice, rate=rate_param)
    
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

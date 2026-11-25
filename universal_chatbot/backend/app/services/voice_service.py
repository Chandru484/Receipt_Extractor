import io
import re
import logging
from typing import Optional, AsyncIterator
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
        # Strip .00 from numbers so TTS does not pronounce "புள்ளி பூஜ்ஜியம் பூஜ்ஜியம்"
        cleaned = re.sub(r"(\d+)\.00\b", r"\1", cleaned)

        # Smooth out bookish suffixes into natural spoken Tamil
        cleaned = re.sub(r"\bஆகும்\b", "", cleaned)
        cleaned = re.sub(r"\bஆவார்\b", "", cleaned)

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


async def generate_speech_stream(
    text: str,
    language: str = "en",
    voice: Optional[str] = None
) -> AsyncIterator[bytes]:
    """
    Generate native neural audio stream (MP3) for Tamil or English.
    """
    clean_text = sanitize_text_for_speech(text, language=language)
    if not clean_text:
        return

    # Select native voice
    selected_voice = voice
    if not selected_voice:
        selected_voice = DEFAULT_VOICES.get(language, DEFAULT_VOICES["en"])

    # Natural conversational pacing (+4% rate removes robotic drag for Tamil neural voice)
    rate_param = "+4%" if language == "ta" else "+0%"
    communicate = edge_tts.Communicate(clean_text, selected_voice, rate=rate_param)
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            yield chunk["data"]

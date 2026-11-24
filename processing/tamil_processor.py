"""Tamil text normalization and legacy font conversion module.

Supports converting legacy 8-bit Tamil font encodings (TSCII, TAB, TAM)
commonly used in Indian billing software (e.g. Tally, Marg ERP, local billing tools)
into standard Unicode Tamil.
"""

import logging
from typing import Any, Dict, List, Union

logger = logging.getLogger(__name__)


def is_legacy_tamil_text(text: str) -> bool:
    """Check if the text contains 8-bit characters typical of legacy Tamil encodings."""
    if not text:
        return False
    # Characters in 0x80 - 0xFF (128 - 255) are standard in TSCII / legacy font maps
    legacy_count = sum(1 for c in text if 128 <= ord(c) <= 255)
    return legacy_count >= 1


def normalize_tamil_text(text: str) -> str:
    """Convert legacy Tamil font-encoded text (TSCII / TAB / TAM) to standard Unicode Tamil.
    
    If the text is already standard Unicode or plain English/digits, returns it untouched.
    """
    if not text or not is_legacy_tamil_text(text):
        return text

    try:
        import tamil.txt2unicode as t2u
        # tscii2unicode safely handles mixed text (keeps English, numbers, symbols intact)
        return t2u.tscii2unicode(text)
    except Exception as exc:
        logger.warning(f"Failed to normalize legacy Tamil text: {exc}")
        return text


def normalize_ocr_lines(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Normalize a list of OCR line dicts, converting any legacy Tamil font text."""
    normalized = []
    for line in lines:
        if isinstance(line, dict):
            line_copy = dict(line)
            if "text" in line_copy and isinstance(line_copy["text"], str):
                line_copy["text"] = normalize_tamil_text(line_copy["text"])
            normalized.append(line_copy)
        else:
            normalized.append(line)
    return normalized

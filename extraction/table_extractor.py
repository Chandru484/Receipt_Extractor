import re
from typing import Any, Dict, List, Optional


HEADER_KEYWORDS = {
    "description", "particulars", "item", "product",
    "qty", "quantity", "rate", "price", "amount", "value"
}

FOOTER_KEYWORDS = {
    "total", "subtotal", "sub total", "tax", "gst", "cgst", "sgst",
    "amount chargeable", "grand total", "net amount", "terms", "bank"
}


def find_table_header_index(lines: List[Dict[str, Any]]) -> Optional[int]:
    """Find the index of the line that represents table column headers."""
    for idx, line in enumerate(lines):
        text = line.get("text", "").lower()
        matched = sum(1 for kw in HEADER_KEYWORDS if kw in text)
        if matched >= 2:
            return idx
    return None


def extract_table_rows_heuristic(lines: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Heuristic table row extractor using line positions and numeric patterns."""
    header_idx = find_table_header_index(lines)
    if header_idx is None:
        return []

    candidate_rows: List[Dict[str, Any]] = []

    for idx in range(header_idx + 1, len(lines)):
        line = lines[idx]
        text = line.get("text", "")
        lower = text.lower()

        # Stop if we hit totals/footer section
        if any(fw in lower for fw in FOOTER_KEYWORDS):
            break

        # Check if line contains numbers (price or quantity)
        numbers = re.findall(r"\b\d+(?:\.\d{1,2})?\b", text)
        if numbers and len(text.strip()) > 3:
            candidate_rows.append({
                "raw_text": text,
                "box": line.get("box"),
                "confidence": line.get("confidence"),
                "numbers": numbers
            })

    return candidate_rows

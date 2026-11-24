import pytest
from processing.tamil_processor import (
    is_legacy_tamil_text,
    normalize_tamil_text,
    normalize_ocr_lines,
)


def test_is_legacy_tamil_text():
    assert is_legacy_tamil_text("¾¢¨½ «Ã¢º¢(UNBRANDED)") is True
    assert is_legacy_tamil_text("Plain English Text 12345") is False
    assert is_legacy_tamil_text("") is False
    assert is_legacy_tamil_text("திணை அரிசி") is False


def test_normalize_tamil_text():
    # Legacy TSCII -> Tamil Unicode
    converted = normalize_tamil_text("¾¢¨½ «Ã¢º¢(UNBRANDED)")
    assert "திணை அரிசி" in converted
    assert "(UNBRANDED)" in converted

    # English should stay untouched
    assert normalize_tamil_text("Siya Seed 100g") == "Siya Seed 100g"
    assert normalize_tamil_text("") == ""


def test_normalize_ocr_lines():
    lines = [
        {"text": "¾¢¨½ «Ã¢º¢", "confidence": 0.95},
        {"text": "Invoice # 10788", "confidence": 0.99},
    ]
    normalized = normalize_ocr_lines(lines)
    assert "திணை அரிசி" in normalized[0]["text"]
    assert normalized[1]["text"] == "Invoice # 10788"

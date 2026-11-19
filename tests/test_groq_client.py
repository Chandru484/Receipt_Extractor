import json
from unittest.mock import MagicMock, patch
import pytest
from ai.groq_client import (
    extract_receipt_with_groq,
    GroqExtractionError,
    _clean_json_response,
    _sanitize_error,
)
from core.config import settings
from schemas.receipt_schema import ReceiptData


def test_clean_json_response():
    markdown_wrapped = "```json\n{\"vendor_name\": \"Store\"}\n```"
    assert _clean_json_response(markdown_wrapped) == "{\"vendor_name\": \"Store\"}"

    plain = "{\"vendor_name\": \"Store\"}"
    assert _clean_json_response(plain) == "{\"vendor_name\": \"Store\"}"


def test_sanitize_error():
    with patch.object(settings, "GROQ_API_KEY", "gsk_primary_secret_123"), \
         patch.object(settings, "GROQ_FALLBACK_API_KEY", "gsk_fallback_secret_456"):
        raw_msg = "Error using gsk_primary_secret_123 and gsk_fallback_secret_456 failed"
        sanitized = _sanitize_error(raw_msg)
        assert "gsk_primary_secret_123" not in sanitized
        assert "gsk_fallback_secret_456" not in sanitized
        assert "[REDACTED_API_KEY]" in sanitized


def test_extract_receipt_with_groq_empty_ocr():
    with pytest.raises(GroqExtractionError, match="did not detect any readable text"):
        extract_receipt_with_groq({"full_text": "   ", "lines": []})


@patch("ai.groq_client.get_groq_client")
def test_extract_receipt_with_groq_success(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    sample_response_data = {
        "document_type": "receipt",
        "vendor_name": "ABC Store",
        "invoice_number": "INV-1025",
        "invoice_date": "2026-11-18",
        "customer_name": None,
        "items": [
            {
                "item_name": "Widget",
                "quantity": 1.0,
                "unit_price": 500.0,
                "total_price": 500.0
            }
        ],
        "subtotal": 500.0,
        "tax": 90.0,
        "grand_total": 590.0,
        "currency": "INR"
    }

    mock_completion = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps(sample_response_data)
    mock_completion.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_completion

    ocr_result = {
        "full_text": "ABC Store INV-1025 Widget 500.00 Total: 590.00",
        "lines": [{"text": "ABC Store", "confidence": 0.99}]
    }

    result = extract_receipt_with_groq(ocr_result)
    assert isinstance(result, ReceiptData)
    assert result.vendor_name == "ABC Store"
    assert result.grand_total == 590.0
    assert len(result.items) == 1


@patch("ai.groq_client.get_groq_client")
def test_extract_receipt_with_fallback_groq_success(mock_get_client):
    """Test that when primary Groq key fails, the fallback key is called and succeeds."""
    mock_primary_client = MagicMock()
    mock_primary_client.chat.completions.create.side_effect = Exception("Rate limit reached on primary")

    mock_fallback_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "document_type": "receipt",
        "vendor_name": "Fallback Vendor",
        "grand_total": 250.0
    })
    mock_fallback_completion = MagicMock()
    mock_fallback_completion.choices = [mock_choice]
    mock_fallback_client.chat.completions.create.return_value = mock_fallback_completion

    def side_effect(api_key=None):
        if api_key == "primary_key_val":
            return mock_primary_client
        return mock_fallback_client

    mock_get_client.side_effect = side_effect

    with patch.object(settings, "GROQ_API_KEY", "primary_key_val"), \
         patch.object(settings, "GROQ_FALLBACK_API_KEY", "fallback_key_val"):
        ocr_result = {
            "full_text": "Fallback Vendor Total: 250.00",
            "lines": [{"text": "Fallback Vendor", "confidence": 0.9}]
        }
        result = extract_receipt_with_groq(ocr_result)
        assert isinstance(result, ReceiptData)
        assert result.vendor_name == "Fallback Vendor"
        assert result.grand_total == 250.0


@patch("ai.groq_client.get_groq_client")
def test_extract_receipt_both_groq_fail(mock_get_client):
    """Test that when both primary and fallback fail, GroqExtractionError is raised."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("Service unavailable")
    mock_get_client.return_value = mock_client

    with patch.object(settings, "GROQ_API_KEY", "primary_key_val"), \
         patch.object(settings, "GROQ_FALLBACK_API_KEY", "fallback_key_val"):
        ocr_result = {
            "full_text": "Vendor Total: 100",
            "lines": [{"text": "Vendor", "confidence": 0.9}]
        }
        with pytest.raises(GroqExtractionError, match="Extraction failed across all Groq API keys"):
            extract_receipt_with_groq(ocr_result)


@patch("ai.groq_client.get_groq_client")
def test_extract_receipt_with_groq_invalid_json(mock_get_client):
    mock_client = MagicMock()
    mock_get_client.return_value = mock_client

    mock_completion = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Not valid JSON {"
    mock_completion.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_completion

    ocr_result = {
        "full_text": "Sample text",
        "lines": [{"text": "Sample text", "confidence": 0.9}]
    }

    with pytest.raises(GroqExtractionError, match="Failed to parse Groq response as JSON"):
        extract_receipt_with_groq(ocr_result)

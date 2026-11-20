import json
from unittest.mock import MagicMock, patch
import pytest
from ai.groq_client import (
    extract_receipt_with_groq,
    get_all_groq_api_keys,
    GroqExtractionError,
    _clean_json_response,
    _sanitize_error,
    _split_multipage_ocr,
    _merge_receipt_pages,
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


def test_multipage_ocr_split_and_merge():
    ocr_result = {
        "full_text": "--- Page 1 ---\nVendor One\nWidget",
        "total_pages": 2,
    }
    pages = _split_multipage_ocr(ocr_result)
    assert len(pages) == 1

    ocr_result["full_text"] = "--- Page 1 ---\nVendor One\nWidget\n\n--- Page 2 ---\nGadget"
    pages = _split_multipage_ocr(ocr_result)
    assert [page_number for page_number, _ in pages] == [1, 2]

    page_one = ReceiptData.model_validate({
        "vendor_name": "Vendor One",
        "items": [{"item_name": "Widget", "page": 1, "total_price": 10}],
    })
    page_two = ReceiptData.model_validate({
        "items": [{"item_name": "Gadget", "page": 2, "total_price": 20}],
    })
    merged = _merge_receipt_pages([(1, page_one), (2, page_two)])
    assert len(merged.items) == 2
    assert [item.page for item in merged.items] == [1, 2]


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


def test_get_all_groq_api_keys_deduplication(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "key_alpha")
    monkeypatch.setattr(settings, "GROQ_API_KEYS", "key_beta, key_gamma")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_API_KEY", "key_delta")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_API_KEYS", "key_gamma, key_epsilon")
    monkeypatch.setenv("GROQ_FALLBACK_API_KEY_1", "key_zeta")

    keys = get_all_groq_api_keys()
    assert keys == ["key_alpha", "key_beta", "key_gamma", "key_delta", "key_epsilon", "key_zeta"]


def test_sanitize_error_multiple_keys(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "gsk_primary_key_abc")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_API_KEY", "gsk_fallback_key_def")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_API_KEYS", "gsk_third_key_ghi, gsk_fourth_key_jkl")

    raw_err = "Auth failed: gsk_primary_key_abc and gsk_third_key_ghi are blocked"
    sanitized = _sanitize_error(raw_err)
    assert "gsk_primary_key_abc" not in sanitized
    assert "gsk_third_key_ghi" not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized


@patch("ai.groq_client.get_groq_client")
def test_extract_receipt_with_multiple_fallback_keys(mock_get_client, monkeypatch):
    """Test that when 1st and 2nd keys fail, 3rd key is invoked and succeeds."""
    monkeypatch.setattr(settings, "GROQ_API_KEY", "key_1")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_API_KEY", "key_2")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_API_KEYS", "key_3")

    mock_client_1 = MagicMock()
    mock_client_1.chat.completions.create.side_effect = Exception("Rate limit reached on key 1")

    mock_client_2 = MagicMock()
    mock_client_2.chat.completions.create.side_effect = Exception("Rate limit reached on key 2")

    mock_client_3 = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({
        "document_type": "receipt",
        "vendor_name": "Third Key Vendor",
        "grand_total": 777.0
    })
    mock_comp = MagicMock()
    mock_comp.choices = [mock_choice]
    mock_client_3.chat.completions.create.return_value = mock_comp

    def get_client_side_effect(api_key=None):
        if api_key == "key_1":
            return mock_client_1
        elif api_key == "key_2":
            return mock_client_2
        elif api_key == "key_3":
            return mock_client_3
        raise ValueError(f"Unexpected key: {api_key}")

    mock_get_client.side_effect = get_client_side_effect

    ocr_result = {
        "full_text": "Third Key Vendor Total: 777.00",
        "lines": [{"text": "Third Key Vendor", "confidence": 0.99}]
    }

    result = extract_receipt_with_groq(ocr_result)
    assert isinstance(result, ReceiptData)
    assert result.vendor_name == "Third Key Vendor"
    assert result.grand_total == 777.0
    assert mock_client_1.chat.completions.create.called
    assert mock_client_2.chat.completions.create.called
    assert mock_client_3.chat.completions.create.called


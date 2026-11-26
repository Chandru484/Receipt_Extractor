import io
from unittest.mock import MagicMock, patch
import pytest

# ---------------------------------------------------------------------------
# Mock PaddleOCR engine BEFORE importing app.main so the TestClient never
# triggers a real PaddleOCR model download / CPU-init during unit tests.
# ---------------------------------------------------------------------------
_mock_ocr_engine = MagicMock()
_mock_ocr_engine.predict.return_value = []

_paddle_patcher = patch(
    "processing.ocr_engine.get_ocr_engine",
    return_value=_mock_ocr_engine
)
_paddle_patcher.start()

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Receipt Extraction API is running"}


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    json_data = response.json()
    assert json_data["status"] == "healthy"
    assert "PaddleOCR" in json_data["ocr_engine"]


def test_extract_unsupported_file_extension():
    fake_file = io.BytesIO(b"fake txt content")
    response = client.post(
        "/extract",
        files={"file": ("test.xyz", fake_file, "text/plain")}
    )
    assert response.status_code == 400
    assert "Unsupported format" in response.json()["detail"]


def test_extract_empty_file():
    empty_file = io.BytesIO(b"")
    response = client.post(
        "/extract",
        files={"file": ("test.jpg", empty_file, "image/jpeg")}
    )
    assert response.status_code == 400
    assert "Uploaded file is empty" in response.json()["detail"]


@patch("app.main.find_extraction_by_file_hash", return_value=None)
@patch("app.main.find_extraction_by_invoice_and_vendor", return_value=None)
@patch("app.main.save_extraction_to_mongodb", return_value="mock_doc_id_123")
@patch("app.main.preprocess_image")
@patch("app.main.process_receipt")
def test_extract_success_mocked(mock_process, mock_preprocess, mock_save, mock_cache_inv, mock_cache_hash):
    mock_preprocess.return_value = "mock_img_array"
    mock_process.return_value = {
        "receipt": {
            "document_type": "receipt",
            "vendor_name": "Mock Mart",
            "invoice_number": "M-101",
            "invoice_date": "2026-11-18",
            "customer_name": None,
            "items": [],
            "subtotal": 100.0,
            "tax": 18.0,
            "grand_total": 118.0,
            "currency": "INR"
        },
        "formatted_display": "Mock Mart Total: 118.00",
        "ocr": {
            "full_text": "Mock Mart M-101 Total: 118.00",
            "lines": ["Mock Mart"],
            "line_count": 1
        }
    }

    file_bytes = io.BytesIO(b"fake image bytes")
    response = client.post(
        "/extract",
        files={"file": ("receipt.jpg", file_bytes, "image/jpeg")}
    )

    assert response.status_code == 200
    res_json = response.json()
    assert res_json["success"] is True
    assert res_json["data"]["vendor_name"] == "Mock Mart"
    assert res_json["data"]["grand_total"] in [118.0, "₹118.00"]
    assert res_json["ocr"]["line_count"] == 1


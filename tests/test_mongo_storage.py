from unittest.mock import MagicMock, patch
from bson import ObjectId
from core.config import settings
from storage.mongo_client import (
    save_extraction_to_mongodb,
    get_stored_extractions,
    get_stored_extraction_by_id,
    check_mongo_connection,
)


def test_save_extraction_disabled():
    with patch.object(settings, "MONGODB_ENABLED", False):
        result = save_extraction_to_mongodb({"success": True})
        assert result is None


def test_save_extraction_success():
    fake_id = ObjectId("507f1f77bcf86cd799439011")
    mock_collection = MagicMock()
    mock_collection.insert_one.return_value.inserted_id = fake_id

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        payload = {
            "success": True,
            "message": "Receipt extracted successfully",
            "data": {"vendor_name": "Test Vendor", "grand_total": 100.0},
        }
        inserted_id = save_extraction_to_mongodb(payload)
        assert inserted_id == str(fake_id)
        mock_collection.insert_one.assert_called_once()
        saved_doc = mock_collection.insert_one.call_args[0][0]
        assert saved_doc["data"]["vendor_name"] == "Test Vendor"
        assert "stored_at" in saved_doc


def test_save_extraction_resilient_to_error():
    mock_collection = MagicMock()
    mock_collection.insert_one.side_effect = Exception("DB connection dropped")

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        payload = {"success": True}
        # Must return None and NOT raise an unhandled exception
        result = save_extraction_to_mongodb(payload)
        assert result is None


def test_get_stored_extractions():
    fake_id = ObjectId("507f1f77bcf86cd799439011")
    mock_collection = MagicMock()
    mock_collection.find.return_value.sort.return_value.skip.return_value.limit.return_value = [
        {"_id": fake_id, "vendor_name": "Test"}
    ]

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        records = get_stored_extractions(limit=10, skip=0)
        assert len(records) == 1
        assert records[0]["_id"] == str(fake_id)
        assert records[0]["vendor_name"] == "Test"


def test_get_stored_extraction_by_id():
    fake_id = ObjectId("507f1f77bcf86cd799439011")
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {"_id": fake_id, "vendor_name": "Test"}

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        # Invalid ID format
        assert get_stored_extraction_by_id("invalid-id") is None

        # Valid ID format
        doc = get_stored_extraction_by_id(str(fake_id))
        assert doc is not None
        assert doc["_id"] == str(fake_id)


def test_check_mongo_connection_disabled():
    with patch.object(settings, "MONGODB_ENABLED", False):
        diag = check_mongo_connection()
        assert diag["status"] == "disabled"

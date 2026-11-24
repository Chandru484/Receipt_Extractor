from unittest.mock import MagicMock, patch
from bson import ObjectId
from core.config import settings
from storage.mongo_client import (
    save_extraction_to_mongodb,
    find_extraction_by_file_hash,
    find_extraction_by_invoice_number,
    find_extraction_by_invoice_and_vendor,
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


def test_save_extraction_skips_duplicate_invoice():
    existing_id = ObjectId("507f1f77bcf86cd799439011")
    mock_collection = MagicMock()
    # Simulate existing record found in MongoDB
    mock_collection.find_one.return_value = {
        "_id": existing_id,
        "data": {"invoice_number": "INV-3337"}
    }

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        payload = {
            "success": True,
            "message": "Receipt extracted successfully",
            "data": {"invoice_number": "INV-3337", "vendor_name": "Test Business"},
        }
        ret_id = save_extraction_to_mongodb(payload)
        # Verify NO insertion occurred
        mock_collection.insert_one.assert_not_called()
        # Verify existing document ID was returned and is_duplicate flag set
        assert ret_id == str(existing_id)
        assert payload.get("is_duplicate") is True


def test_save_extraction_inserts_when_invoice_not_found():
    new_id = ObjectId("507f1f77bcf86cd799439022")
    mock_collection = MagicMock()
    # Simulate not found
    mock_collection.find_one.return_value = None
    mock_collection.insert_one.return_value.inserted_id = new_id

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        payload = {
            "success": True,
            "message": "Receipt extracted successfully",
            "data": {"invoice_number": "INV-9999", "vendor_name": "New Vendor"},
        }
        ret_id = save_extraction_to_mongodb(payload)
        # Verify insertion occurred
        mock_collection.insert_one.assert_called_once()
        assert ret_id == str(new_id)
        assert payload.get("is_duplicate") is False


def test_find_extraction_by_invoice_number():
    fake_id = ObjectId("507f1f77bcf86cd799439033")
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {
        "_id": fake_id,
        "data": {"invoice_number": "INV-123"}
    }

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        doc = find_extraction_by_invoice_number("INV-123")
        assert doc is not None
        assert doc["_id"] == str(fake_id)
        mock_collection.find_one.assert_called_once()

        # Empty / None invoice returns None without calling find_one
        mock_collection.reset_mock()
        assert find_extraction_by_invoice_number("") is None
        assert find_extraction_by_invoice_number(None) is None
        mock_collection.find_one.assert_not_called()


def test_find_extraction_by_file_hash():
    fake_id = ObjectId("507f1f77bcf86cd799439044")
    sample_hash = "8d99b9d14ee81a4f8ce70782eace996174186be6e6906f9a01a5a545779b128f"
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {
        "_id": fake_id,
        "file_hash": sample_hash,
        "data": {"vendor_name": "Test Vendor"}
    }

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        # Successful lookup by file hash
        doc = find_extraction_by_file_hash(sample_hash)
        assert doc is not None
        assert doc["_id"] == str(fake_id)
        assert doc["file_hash"] == sample_hash
        mock_collection.find_one.assert_called_once_with({"file_hash": sample_hash})

        # Empty / None hash returns None immediately
        mock_collection.reset_mock()
        assert find_extraction_by_file_hash("") is None
        assert find_extraction_by_file_hash(None) is None
        mock_collection.find_one.assert_not_called()


def test_save_extraction_deduplicates_by_file_hash():
    existing_id = ObjectId("507f1f77bcf86cd799439055")
    sample_hash = "8d99b9d14ee81a4f8ce70782eace996174186be6e6906f9a01a5a545779b128f"
    mock_collection = MagicMock()
    # Simulate existing record found by file hash
    mock_collection.find_one.return_value = {
        "_id": existing_id,
        "file_hash": sample_hash,
        "stored_at": "2026-11-24T10:00:00+00:00",
        "data": {"vendor_name": "Cached Vendor"}
    }

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        payload = {
            "success": True,
            "message": "Receipt extracted successfully",
            "data": {"vendor_name": "Cached Vendor"},
        }
        ret_id = save_extraction_to_mongodb(payload, file_hash=sample_hash, file_name="invoice.pdf")
        # Verify no insert_one was called
        mock_collection.insert_one.assert_not_called()
        # Verify replace_one was called with ObjectId (NOT string)
        mock_collection.replace_one.assert_called_once()
        filter_arg = mock_collection.replace_one.call_args[0][0]
        assert filter_arg == {"_id": existing_id}
        assert isinstance(filter_arg["_id"], ObjectId)
        # Verify payload status
        assert ret_id == str(existing_id)
        assert payload.get("is_duplicate") is True
        assert payload.get("document_id") == str(existing_id)


def test_save_extraction_deduplicates_by_invoice_uses_objectid():
    existing_id = ObjectId("507f1f77bcf86cd799439066")
    mock_collection = MagicMock()
    # First find_one (by hash) returns None; second find_one (by invoice) returns existing doc
    mock_collection.find_one.side_effect = [
        None,  # find by file_hash
        {"_id": existing_id, "data": {"invoice_number": "INV-10788"}}  # find by invoice
    ]

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        payload = {
            "success": True,
            "data": {"invoice_number": "INV-10788"},
        }
        ret_id = save_extraction_to_mongodb(payload, file_hash="newhash123", file_name="bill.jpg")
        mock_collection.insert_one.assert_not_called()
        mock_collection.replace_one.assert_called_once()
        filter_arg = mock_collection.replace_one.call_args[0][0]
        # Must be ObjectId, not string
        assert filter_arg == {"_id": existing_id}
        assert isinstance(filter_arg["_id"], ObjectId)
        assert ret_id == str(existing_id)
        assert payload.get("is_duplicate") is True


def test_find_extraction_by_invoice_and_vendor():
    fake_id = ObjectId("507f1f77bcf86cd799439077")
    mock_collection = MagicMock()
    mock_collection.find_one.return_value = {
        "_id": fake_id,
        "data": {
            "invoice_number": "3",
            "vendor_name": "SPT EXPORT"
        }
    }

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        # 1. Matching invoice AND matching vendor returns the document
        doc = find_extraction_by_invoice_and_vendor("3", "SPT EXPORT")
        assert doc is not None
        assert doc["_id"] == str(fake_id)
        mock_collection.find_one.assert_called_once()
        query = mock_collection.find_one.call_args[0][0]
        # Verify query combines both invoice and vendor in $and
        assert "$and" in query
        assert len(query["$and"]) == 2

        # 2. When collection returns None (different vendor or different invoice), returns None
        mock_collection.find_one.return_value = None
        assert find_extraction_by_invoice_and_vendor("3", "OTHER VENDOR") is None


def test_same_vendor_multiple_receipts_are_distinct():
    """Verify that multiple receipts from the same vendor with different invoice numbers are stored distinctly."""
    mock_collection = MagicMock()
    # No existing record for invoice 4 from SPT EXPORT
    mock_collection.find_one.return_value = None
    new_id_4 = ObjectId("507f1f77bcf86cd799439088")
    mock_collection.insert_one.return_value.inserted_id = new_id_4

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        payload_inv_4 = {
            "success": True,
            "data": {
                "invoice_number": "4",
                "vendor_name": "SPT EXPORT",
                "grand_total": "₹500.00"
            }
        }
        ret_id = save_extraction_to_mongodb(
            payload_inv_4,
            vendor_name="SPT EXPORT",
            invoice_number="4"
        )
        # Must INSERT a new document (NOT overwrite existing invoice 3)
        mock_collection.insert_one.assert_called_once()
        mock_collection.replace_one.assert_not_called()
        assert ret_id == str(new_id_4)
        assert payload_inv_4.get("is_duplicate") is False


def test_different_vendors_same_invoice_no_collision():
    """Verify that if two different vendors both have invoice #3, they do not collide."""
    mock_collection = MagicMock()
    # find_one query requires BOTH invoice=3 AND vendor=VSMTEXTILES -> returns None
    mock_collection.find_one.return_value = None
    new_vsm_id = ObjectId("507f1f77bcf86cd799439099")
    mock_collection.insert_one.return_value.inserted_id = new_vsm_id

    with patch("storage.mongo_client.get_receipt_collection", return_value=mock_collection):
        payload_vsm = {
            "success": True,
            "data": {
                "invoice_number": "3",
                "vendor_name": "VSMTEXTILES",
                "grand_total": "₹1200.00"
            }
        }
        ret_id = save_extraction_to_mongodb(
            payload_vsm,
            vendor_name="VSMTEXTILES",
            invoice_number="3"
        )
        # Must INSERT a new document for VSMTEXTILES (NOT overwrite SPT EXPORT's invoice 3)
        mock_collection.insert_one.assert_called_once()
        mock_collection.replace_one.assert_not_called()
        assert ret_id == str(new_vsm_id)
        assert payload_vsm.get("is_duplicate") is False


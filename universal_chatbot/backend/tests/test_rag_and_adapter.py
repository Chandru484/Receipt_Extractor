import io
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from universal_chatbot.backend.app.services.document_parser import chunk_text, extract_text_from_bytes
from universal_chatbot.backend.app.services.rag_service import rag_service, _compute_relevance_score, _tokenize
from universal_chatbot.backend.app.application_adapters.mongodb_adapter import app_mongo_adapter
from universal_chatbot.backend.app.main import app


@pytest.fixture(autouse=True)
def mock_platform_mongo():
    """Mock platform MongoDB for all unit tests."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db
    with patch("universal_chatbot.backend.app.database.mongodb.get_mongo_client", return_value=mock_client), \
         patch("universal_chatbot.backend.app.database.mongodb.get_chatbot_db", return_value=mock_db), \
         patch("universal_chatbot.backend.app.database.indexes.ensure_indexes"):
        yield


def test_chunk_text_algorithm():
    """Verify semantic paragraph chunking."""
    sample_text = (
        "Paragraph 1: Introduction to Universal Chatbot Platform.\n\n"
        "Paragraph 2: Features include multi-tenancy, Tamil and English support, and voice synthesis.\n\n"
        "Paragraph 3: It connects to MongoDB Atlas with database isolation."
    )
    chunks = chunk_text(sample_text, chunk_size=100, chunk_overlap=20)
    assert len(chunks) >= 2
    assert all("text" in c and "chunk_index" in c for c in chunks)
    assert chunks[0]["chunk_index"] == 0


def test_tokenize_multilingual():
    """Verify tokenizer supports English words, filenames, and Tamil characters."""
    en_tokens = _tokenize("Hello world! Tell me about GST.pdf file?")
    assert "hello" in en_tokens
    assert "world" in en_tokens
    assert "gst" in en_tokens
    assert "pdf" in en_tokens

    ta_tokens = _tokenize("வணக்கம்! நலமாக இருக்கிறீர்களா?")
    assert "வணக்கம்" in ta_tokens
    assert len(ta_tokens) >= 2


def test_rag_session_document_fallback():
    """Verify RAG retrieves session-uploaded document chunks even for broad summary queries."""
    mock_chunks_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.limit.return_value = [
        {
            "chunk_id": "chk_1",
            "source_id": "doc_gst",
            "source_name": "GST.pdf",
            "content": "MEGA RASI TAPES Tax Invoice Total 27195.00",
            "chunk_index": 0,
            "is_user_document": True,
        }
    ]
    mock_kb_cursor = MagicMock()
    mock_kb_cursor.limit.return_value = []
    mock_chunks_col.find.side_effect = [mock_cursor, mock_kb_cursor]

    with patch("universal_chatbot.backend.app.services.rag_service.get_document_chunks_collection", return_value=mock_chunks_col):
        results = rag_service.retrieve_relevant_chunks(
            tenant_id="ten_default",
            website_id="site_demo",
            query="summarize this uploaded document please",
            session_id="sess_xyz",
            top_k=5,
        )
        assert len(results) == 1
        assert results[0]["source_name"] == "GST.pdf"
        assert results[0]["is_user_document"] is True


def test_relevance_scoring():
    """Verify relevance scoring ranks matching text higher."""
    query_tokens = ["invoice", "amazon"]
    chunk1 = "Here is the invoice from Amazon Inc for $45.99."
    chunk2 = "The restaurant menu offers pizza and beverages."

    score1 = _compute_relevance_score(query_tokens, chunk1)
    score2 = _compute_relevance_score(query_tokens, chunk2)
    assert score1 > score2
    assert score1 > 1.0


def test_rag_ingest_and_retrieve():
    """Verify RAG document ingestion and scoped retrieval."""
    mock_chunks_col = MagicMock()
    mock_user_col = MagicMock()

    with patch("universal_chatbot.backend.app.services.rag_service.get_document_chunks_collection", return_value=mock_chunks_col), \
         patch("universal_chatbot.backend.app.services.rag_service.get_user_documents_collection", return_value=mock_user_col):

        file_bytes = b"Return policy: Customers can return items within 30 days of purchase for a full refund."
        res = rag_service.ingest_document(
            tenant_id="ten_test",
            website_id="site_test",
            filename="return_policy.txt",
            file_bytes=file_bytes,
            conversation_id="conv_123",
            session_id="sess_abc",
        )
        assert res["filename"] == "return_policy.txt"
        assert res["chunk_count"] >= 1
        assert res["is_user_document"] is True
        mock_chunks_col.insert_many.assert_called_once()


def test_app_mongo_adapter_query():
    """Verify application database adapter executes safe filtered query."""
    mock_app_col = MagicMock()
    mock_app_col.find_one.return_value = {
        "website_id": "site_demo",
        "target_uri": "mongodb://localhost:27017",
        "target_db": "receipt_db",
        "allowed_collection": "Receipt_Extraction",
        "allowed_fields": ["vendor_name", "total_amount", "date"],
        "status": "active",
    }

    mock_target_db = MagicMock()
    mock_target_col = MagicMock()
    mock_target_col.find.return_value.sort.return_value.limit.return_value = [
        {"vendor_name": "Walmart", "total_amount": "54.20", "date": "15-11-2026"}
    ]
    mock_target_db.__getitem__.return_value = mock_target_col

    mock_client = MagicMock()
    mock_client.__getitem__.return_value = mock_target_db

    with patch("universal_chatbot.backend.app.application_adapters.mongodb_adapter.get_app_connections_collection", return_value=mock_app_col), \
         patch.object(app_mongo_adapter, "_get_client", return_value=mock_client):

        data = app_mongo_adapter.query_application_data(
            website_id="site_demo",
            user_query="Show me receipts from Walmart",
        )
        assert data is not None
        assert data["collection"] == "Receipt_Extraction"
        assert len(data["records"]) == 1
        assert data["records"][0]["vendor_name"] == "Walmart"


def test_document_upload_endpoint():
    """Verify POST /api/v1/documents/upload endpoint."""
    mock_site = {"website_id": "site_demo", "tenant_id": "ten_default"}
    mock_ingest_res = {
        "source_id": "doc_test123",
        "filename": "sample_invoice.txt",
        "chunk_count": 2,
        "total_chars": 150,
        "is_user_document": True,
    }

    with patch("universal_chatbot.backend.app.main.ensure_indexes"), \
         patch("universal_chatbot.backend.app.api.v1.document_routes.get_website_by_id", return_value=mock_site), \
         patch("universal_chatbot.backend.app.api.v1.document_routes.rag_service.ingest_document", return_value=mock_ingest_res):

        client = TestClient(app)
        file_payload = ("sample_invoice.txt", b"Vendor: TechMart\nAmount: $250.00\nDate: 20-11-2026", "text/plain")
        
        resp = client.post(
            "/api/v1/documents/upload",
            data={"website_id": "site_demo", "session_id": "sess_001"},
            files={"file": file_payload},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["document_id"] == "doc_test123"
        assert data["chunk_count"] == 2
        assert "sample_invoice.txt" in data["message"]

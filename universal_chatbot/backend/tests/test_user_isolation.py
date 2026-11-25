import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from universal_chatbot.backend.app.main import app
from universal_chatbot.backend.app.application_adapters.mongodb_adapter import ApplicationMongoAdapter

client = TestClient(app)


def test_user_data_isolation_in_database_adapter():
    """Verify that when user_id is provided, database queries strictly enforce user boundary."""
    adapter = ApplicationMongoAdapter()

    # Mock MongoDB collection
    mock_col = MagicMock()
    mock_cursor = MagicMock()
    mock_cursor.sort.return_value.limit.return_value = [
        {"user_id": "user_alice", "vendor_name": "Alice Supermarket", "total_amount": 450.0}
    ]
    mock_col.find.return_value = mock_cursor

    mock_db = MagicMock()
    mock_db.__getitem__.return_value = mock_col

    mock_client = MagicMock()
    mock_client.__getitem__.return_value = mock_db

    mock_conn = {
        "website_id": "site_demo",
        "target_uri": "mongodb://localhost:27017",
        "target_db": "test_db",
        "allowed_collection": "receipts",
        "user_id_field": "user_id",
        "allowed_fields": ["vendor_name", "total_amount"],
        "status": "active"
    }

    with patch.object(adapter, "get_connection_config", return_value=mock_conn), \
         patch.object(adapter, "_get_client", return_value=mock_client):

        # Alice queries
        res_alice = adapter.query_application_data(
            website_id="site_demo",
            user_query="show my receipts",
            user_id="user_alice"
        )
        assert res_alice is not None
        find_call_args = mock_col.find.call_args[0][0]
        # Verify query filter contains user_id restriction
        assert "$or" in find_call_args
        assert any(cond.get("user_id") == "user_alice" for cond in find_call_args["$or"])


def test_cross_user_data_leakage_prevention():
    """Verify Alice cannot see Bob's data through the Chatbot API."""
    mock_site = {
        "website_id": "site_demo",
        "tenant_id": "ten_default",
        "name": "Demo Site",
        "widget_config": {"bot_name": "Universal Assistant", "enable_tawk_to": False}
    }

    mock_reply = {
        "reply": "You have 1 receipt on file for Alice Supermarket (Total: 450).",
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
    }

    with patch("universal_chatbot.backend.app.main.ensure_indexes"), \
         patch("universal_chatbot.backend.app.services.chat_orchestrator.get_website_by_id", return_value=mock_site), \
         patch("universal_chatbot.backend.app.services.chat_orchestrator.app_mongo_adapter.query_application_data") as mock_db_query, \
         patch("universal_chatbot.backend.app.ai.multi_provider.ai_engine.generate_chat_response", return_value=mock_reply), \
         patch("universal_chatbot.backend.app.database.collections.get_conversations_collection", return_value=MagicMock()), \
         patch("universal_chatbot.backend.app.database.collections.get_messages_collection", return_value=MagicMock()):

        mock_db_query.return_value = {
            "collection": "Receipt_Extraction",
            "record_count": 1,
            "records": [{"user_id": "user_alice", "vendor_name": "Alice Supermarket", "grand_total": "450"}]
        }

        # Request sent by Alice
        req = {
            "website_id": "site_demo",
            "message": "Show all receipts in database",
            "user_id": "user_alice",
            "role": "user"
        }
        resp = client.post("/api/v1/chat/message", json=req)
        assert resp.status_code == 200

        # Verify adapter was called with verified_user_id='user_alice'
        called_user_id = mock_db_query.call_args[1].get("user_id")
        assert called_user_id == "user_alice"


def test_role_based_suggestions_isolation():
    """Verify Admin, Worker, and User receive strictly isolated question packages."""
    resp_adm = client.get("/api/v1/projects/site_demo/suggestions?role=admin")
    resp_wrk = client.get("/api/v1/projects/site_demo/suggestions?role=worker")
    resp_usr = client.get("/api/v1/projects/site_demo/suggestions?role=user")

    assert resp_adm.status_code == 200
    assert resp_wrk.status_code == 200
    assert resp_usr.status_code == 200

    adm_questions = resp_adm.json()["suggested_questions"]
    wrk_questions = resp_wrk.json()["suggested_questions"]
    usr_questions = resp_usr.json()["suggested_questions"]

    # Assert packages are completely distinct
    assert adm_questions != wrk_questions
    assert wrk_questions != usr_questions
    assert any("revenue" in q.lower() or "audit" in q.lower() or "approval" in q.lower() for q in adm_questions)
    assert any("task" in q.lower() or "shift" in q.lower() or "safety" in q.lower() for q in wrk_questions)

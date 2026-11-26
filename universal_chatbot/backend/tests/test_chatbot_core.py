import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from universal_chatbot.backend.app.core.security import encrypt_secret, decrypt_secret, create_admin_jwt, verify_admin_jwt
from universal_chatbot.backend.app.schemas.tenant_schema import TenantCreate, WebsiteCreate
from universal_chatbot.backend.app.services.tenant_service import create_tenant, register_website
from universal_chatbot.backend.app.ai.multi_provider import MultiProviderAIEngine
from universal_chatbot.backend.app.main import app


@pytest.fixture(autouse=True)
def mock_platform_mongo():
    """Mock platform MongoDB for all unit tests to prevent network I/O."""
    mock_client = MagicMock()
    mock_db = MagicMock()
    mock_client.__getitem__.return_value = mock_db
    with patch("universal_chatbot.backend.app.database.mongodb.get_mongo_client", return_value=mock_client), \
         patch("universal_chatbot.backend.app.database.mongodb.get_chatbot_db", return_value=mock_db), \
         patch("universal_chatbot.backend.app.database.indexes.ensure_indexes"):
        yield


def test_encryption_and_decryption():
    """Verify AES-256-GCM secret encryption and decryption."""
    original = "mongodb+srv://admin:SecretPass123@cluster.net"
    encrypted = encrypt_secret(original)
    assert encrypted != original
    decrypted = decrypt_secret(encrypted)
    assert decrypted == original


def test_admin_jwt_lifecycle():
    """Verify JWT token creation and verification."""
    payload = {"admin_id": "adm_123", "role": "superadmin"}
    token = create_admin_jwt(payload, expires_in_seconds=3600)
    assert isinstance(token, str)

    verified = verify_admin_jwt(token)
    assert verified is not None
    assert verified["admin_id"] == "adm_123"
    assert verified["role"] == "superadmin"


def test_tenant_and_website_registration():
    """Verify tenant and website registration logic."""
    mock_tenants = MagicMock()
    mock_websites = MagicMock()

    with patch("universal_chatbot.backend.app.database.collections.get_tenants_collection", return_value=mock_tenants), \
         patch("universal_chatbot.backend.app.database.collections.get_websites_collection", return_value=mock_websites):

        t_res = create_tenant(TenantCreate(
            name="Acme Corp",
            admin_email="admin@acme.com",
            admin_password="Password123!"
        ))
        assert t_res.tenant_id.startswith("ten_")
        assert t_res.name == "Acme Corp"
        mock_tenants.insert_one.assert_called_once()

        w_res = register_website(WebsiteCreate(
            tenant_id=t_res.tenant_id,
            name="Acme Main Portal",
            allowed_domains=["acme.com", "portal.acme.com"]
        ))
        assert w_res.website_id.startswith("site_")
        assert w_res.tenant_id == t_res.tenant_id
        mock_websites.insert_one.assert_called_once()


def test_ai_multi_provider_emergency_fallback():
    """Verify emergency fallback when all providers are unavailable."""
    engine = MultiProviderAIEngine()
    engine.groq_provider = MagicMock()
    engine.groq_provider.is_available.return_value = False
    engine.fallback_provider = MagicMock()
    engine.fallback_provider.is_available.return_value = False

    # English fallback
    res_en = engine.generate_chat_response([{"role": "user", "content": "Hello"}], language="en")
    assert res_en["provider"] == "emergency_fallback"
    assert "AI service is currently experiencing high demand" in res_en["reply"]

    # Tamil fallback
    res_ta = engine.generate_chat_response([{"role": "user", "content": "வணக்கம்"}], language="ta")
    assert res_ta["provider"] == "emergency_fallback"
    assert "மன்னிக்கவும்" in res_ta["reply"]


def test_health_check_endpoint():
    """Verify FastAPI /health endpoint."""
    with patch("universal_chatbot.backend.app.main.check_mongo_health", return_value={"status": "connected", "database": "chatbot_platform_db"}), \
         patch("universal_chatbot.backend.app.main.ensure_indexes"):
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Universal AI Chatbot Platform"
        assert data["mongodb"]["status"] == "connected"


def test_widget_script_endpoint():
    """Verify FastAPI serves /widget.js."""
    with patch("universal_chatbot.backend.app.main.ensure_indexes"):
        client = TestClient(app)
        resp = client.get("/widget.js")
        assert resp.status_code == 200
        assert "attachShadow" in resp.text


def test_chat_message_endpoint():
    """Verify FastAPI /api/v1/chat/message endpoint."""
    mock_reply = {
        "reply": "Welcome to our platform! How can I help you?",
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "latency": 0.12,
        "tokens_used": 25,
    }

    mock_site = {
        "website_id": "site_demo",
        "tenant_id": "ten_default",
        "name": "Demo Site",
        "widget_config": {
            "bot_name": "Universal Assistant",
            "enable_tawk_to": False
        }
    }

    with patch("universal_chatbot.backend.app.main.ensure_indexes"), \
         patch("universal_chatbot.backend.app.services.chat_orchestrator.get_website_by_id", return_value=mock_site), \
         patch("universal_chatbot.backend.app.ai.multi_provider.ai_engine.generate_chat_response", return_value=mock_reply), \
         patch("universal_chatbot.backend.app.database.collections.get_conversations_collection", return_value=MagicMock()), \
         patch("universal_chatbot.backend.app.database.collections.get_messages_collection", return_value=MagicMock()):

        client = TestClient(app)
        req_payload = {
            "website_id": "site_demo",
            "message": "What services do you offer?",
            "language": "en"
        }
        resp = client.post("/api/v1/chat/message", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["reply"] == "Welcome to our platform! How can I help you?"
        assert data["language"] == "en"
        assert "conversation_id" in data


def test_website_action_and_tamil_voice_recognition():
    """Verify Tamil command auto-detects 'ta' language, triggers website action, and preserves is_voice."""
    mock_reply = {
        "reply": "நிச்சயமாக! சமீபத்திய அறிக்கை திரையில் காட்டப்படுகிறது.",
        "provider": "groq",
        "model": "llama-3.3-70b-versatile",
        "latency": 0.15,
        "tokens_used": 30,
    }

    mock_site = {
        "website_id": "site_demo",
        "tenant_id": "ten_default",
        "name": "Demo Site",
        "widget_config": {
            "bot_name": "Universal Assistant",
            "enable_tawk_to": False
        }
    }

    with patch("universal_chatbot.backend.app.main.ensure_indexes"), \
         patch("universal_chatbot.backend.app.services.chat_orchestrator.get_website_by_id", return_value=mock_site), \
         patch("universal_chatbot.backend.app.ai.multi_provider.ai_engine.generate_chat_response", return_value=mock_reply), \
         patch("universal_chatbot.backend.app.database.collections.get_conversations_collection", return_value=MagicMock()), \
         patch("universal_chatbot.backend.app.database.collections.get_messages_collection", return_value=MagicMock()):

        client = TestClient(app)
        # Even if initial language was set to 'en', speaking in Tamil must auto-detect 'ta' and trigger show_latest_report
        req_payload = {
            "website_id": "site_demo",
            "message": "சமீபத்திய அறிக்கையைக் காட்டு",
            "language": "en",
            "is_voice": True,
        }
        resp = client.post("/api/v1/chat/message", json=req_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "ta"
        assert data["is_voice"] is True
        assert data["action"] is not None
        assert data["action"]["action_type"] == "show_latest_report"
        assert data["action"]["target"] == "#outputCard"


def test_delete_and_edit_message():
    """Verify deleting and editing messages via chat routes."""
    mock_messages = MagicMock()
    mock_convs = MagicMock()

    mock_messages.find_one.return_value = {
        "message_id": "msg_test123",
        "conversation_id": "conv_test123",
        "user_message": "Original query",
        "bot_reply": "Original answer",
    }
    mock_messages.delete_one.return_value = MagicMock(deleted_count=1)
    mock_messages.update_one.return_value = MagicMock(matched_count=1)

    with patch("universal_chatbot.backend.app.database.collections.get_messages_collection", return_value=mock_messages), \
         patch("universal_chatbot.backend.app.database.collections.get_conversations_collection", return_value=mock_convs):

        client = TestClient(app)

        # 1. Edit message
        edit_resp = client.put("/api/v1/chat/messages/msg_test123", json={"message": "Updated query"})
        assert edit_resp.status_code == 200
        assert edit_resp.json()["success"] is True
        assert edit_resp.json()["updated_message"] == "Updated query"

        # 2. Delete message
        del_resp = client.delete("/api/v1/chat/messages/msg_test123")
        assert del_resp.status_code == 200
        assert del_resp.json()["success"] is True
        assert del_resp.json()["message_id"] == "msg_test123"


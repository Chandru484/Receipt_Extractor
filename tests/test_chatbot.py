from unittest.mock import MagicMock, patch
import pytest
from core.config import settings
from schemas.chat_schema import ChatRequest, ChatResponse, ChatMessage
from ai.chatbot import ask_chatbot, ESCALATION_PATTERNS


def test_chat_request_schema():
    req = ChatRequest(
        message="What file formats are supported?",
        history=[ChatMessage(role="user", content="Hi"), ChatMessage(role="assistant", content="Hello!")]
    )
    assert req.message == "What file formats are supported?"
    assert len(req.history) == 2


def test_escalation_detection_voice():
    with patch("ai.chatbot.get_groq_client") as mock_get_client:
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "Sure, connecting to voice support."
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        req = ChatRequest(message="Can I send a voice message with my question?")
        res = ask_chatbot(req)

        assert res.escalate_to_tawk is True
        assert res.escalation_reason == "voice_message"
        assert len(res.suggested_questions) > 0


def test_escalation_detection_image_upload():
    with patch("ai.chatbot.get_groq_client") as mock_get_client:
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "You can upload images to our human agent."
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        req = ChatRequest(message="I want to upload an image of my receipt to ask questions")
        res = ask_chatbot(req)

        assert res.escalate_to_tawk is True
        assert res.escalation_reason == "image_upload"


def test_normal_project_question_no_forced_escalation():
    with patch("ai.chatbot.get_groq_client") as mock_get_client:
        mock_client = MagicMock()
        mock_choice = MagicMock()
        mock_choice.message.content = "We support PDF, JPG, PNG, WebP, and BMP files up to 10MB."
        mock_resp = MagicMock()
        mock_resp.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_resp
        mock_get_client.return_value = mock_client

        req = ChatRequest(message="What file formats are supported?")
        res = ask_chatbot(req)

        assert res.escalate_to_tawk is False
        assert "PDF" in res.reply


def test_chatbot_with_multiple_fallback_keys(monkeypatch):
    monkeypatch.setattr(settings, "GROQ_API_KEY", "chat_key_1")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_API_KEY", "chat_key_2")
    monkeypatch.setattr(settings, "GROQ_FALLBACK_API_KEYS", "chat_key_3")

    mock_c1 = MagicMock()
    mock_c1.chat.completions.create.side_effect = Exception("Rate limit on key 1")

    mock_c2 = MagicMock()
    mock_c2.chat.completions.create.side_effect = Exception("Rate limit on key 2")

    mock_c3 = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Chatbot reply from key 3"
    mock_resp = MagicMock()
    mock_resp.choices = [mock_choice]
    mock_c3.chat.completions.create.return_value = mock_resp

    with patch("ai.chatbot.get_groq_client") as mock_get_client:
        def get_client_side_effect(api_key=None):
            if api_key == "chat_key_1":
                return mock_c1
            elif api_key == "chat_key_2":
                return mock_c2
            elif api_key == "chat_key_3":
                return mock_c3
            raise ValueError(f"Unexpected key: {api_key}")

        mock_get_client.side_effect = get_client_side_effect

        req = ChatRequest(message="What is the extraction accuracy?")
        res = ask_chatbot(req)

        assert res.escalate_to_tawk is False
        assert res.reply == "Chatbot reply from key 3"
        assert mock_c1.chat.completions.create.called
        assert mock_c2.chat.completions.create.called
        assert mock_c3.chat.completions.create.called



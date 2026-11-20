from unittest.mock import MagicMock, patch
import pytest
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


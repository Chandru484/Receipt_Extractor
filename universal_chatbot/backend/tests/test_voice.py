import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi.testclient import TestClient

from universal_chatbot.backend.app.services.voice_service import sanitize_text_for_speech, DEFAULT_VOICES
from universal_chatbot.backend.app.main import app


def test_sanitize_text_tamil():
    """Verify markdown, table pipes, and symbols are converted into fluent spoken Tamil."""
    raw = (
        "### வரி இன்பாய்ஸ்\n"
        "| எண் | பொருள் | விலை |\n"
        "|---|---|---|\n"
        "| 1 | அரிசி | ₹500 |\n"
        "GST: 5% & மொத்தம்: ₹525"
    )
    cleaned = sanitize_text_for_speech(raw, language="ta")
    assert "###" not in cleaned
    assert "|" not in cleaned
    assert "ரூபாய்" in cleaned
    assert "சதவீதம்" in cleaned
    assert "ஜி எஸ் டி" in cleaned



def test_sanitize_text_english():
    """Verify markdown and currency symbols are converted to spoken English."""
    raw = "**Total**: ₹1,200 & Discount: 10%"
    cleaned = sanitize_text_for_speech(raw, language="en")
    assert "**" not in cleaned
    assert "Rupees" in cleaned
    assert "percent" in cleaned


def test_voice_endpoints():
    """Verify /api/v1/voice/voices and /api/v1/voice/tts endpoints."""
    with patch("universal_chatbot.backend.app.main.ensure_indexes"):
        client = TestClient(app)

        # 1. Test voice listing
        resp_list = client.get("/api/v1/voice/voices")
        assert resp_list.status_code == 200
        data = resp_list.json()
        assert "tamil" in data
        assert any("ta-IN-PallaviNeural" in v["id"] for v in data["tamil"])

        # 2. Test TTS endpoint with mock stream
        async def fake_stream(*args, **kwargs):
            yield b"FAKE_MP3_BYTES"

        with patch("universal_chatbot.backend.app.api.v1.voice_routes.generate_speech_stream", side_effect=fake_stream):
            resp_tts = client.get("/api/v1/voice/tts?text=வணக்கம்&language=ta")
            assert resp_tts.status_code == 200
            assert resp_tts.headers["content-type"] == "audio/mpeg"
            assert resp_tts.content == b"FAKE_MP3_BYTES"

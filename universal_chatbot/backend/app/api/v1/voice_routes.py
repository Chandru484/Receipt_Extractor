import urllib.parse
import asyncio
from typing import Optional
from fastapi import APIRouter, Query, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from universal_chatbot.backend.app.services.voice_service import (
    generate_speech_stream,
    prewarm_tts_cache,
    DEFAULT_VOICES,
)

router = APIRouter(prefix="/voice", tags=["Voice & Speech"])


@router.api_route("/warmup", methods=["GET", "POST"], summary="Pre-warm TTS connections and caches on mic open")
async def voice_warmup():
    """
    Called when the user taps mic button or enters live voice call mode.
    Pre-warms DNS, TLS, and Edge-TTS socket so zero cold-start delay occurs when response arrives.
    """
    try:
        asyncio.create_task(prewarm_tts_cache("சரி", language="ta"))
        return {"status": "warmed", "voice": DEFAULT_VOICES["ta"]}
    except Exception as exc:
        return {"status": "ok", "error": str(exc)}


class TTSRequest(BaseModel):
    text: str
    language: str = "en"
    voice: Optional[str] = None


@router.get("/tts", summary="Generate streaming Neural Text-to-Speech audio")
async def text_to_speech_get(
    text: str = Query(..., min_length=1, max_length=5000, description="Text to synthesize"),
    language: str = Query("en", description="Target language: 'ta' for Tamil, 'en' for English"),
    voice: Optional[str] = Query(None, description="Optional custom voice short name"),
):
    """
    Stream high-definition, fluent neural speech (MP3) in Tamil or English.
    Tamil uses 'ta-IN-PallaviNeural' for crystal-clear native human pronunciation.
    """
    decoded_text = urllib.parse.unquote(text).strip()
    if not decoded_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text cannot be empty.")

    try:
        audio_stream = generate_speech_stream(
            text=decoded_text,
            language=language,
            voice=voice,
        )
        return StreamingResponse(
            audio_stream,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": "inline; filename=speech.mp3",
                "Accept-Ranges": "bytes",
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS generation failed: {str(exc)}"
        )


@router.post("/tts", summary="Generate Neural Text-to-Speech audio from JSON body")
async def text_to_speech_post(req: TTSRequest):
    """
    POST variant for generating high-definition neural speech from larger texts.
    """
    if not req.text.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text cannot be empty.")

    try:
        audio_stream = generate_speech_stream(
            text=req.text,
            language=req.language,
            voice=req.voice,
        )
        return StreamingResponse(
            audio_stream,
            media_type="audio/mpeg",
            headers={
                "Cache-Control": "public, max-age=3600",
                "Content-Disposition": "inline; filename=speech.mp3",
                "Accept-Ranges": "bytes",
            }
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"TTS generation failed: {str(exc)}"
        )


@router.get("/voices", summary="List supported high-definition neural voices")
def list_voices():
    """Returns available high quality neural voices for Tamil and English."""
    return {
        "tamil": [
            {"id": "ta-IN-PallaviNeural", "name": "Pallavi (Native Tamil Female - Recommended)", "gender": "female"},
            {"id": "ta-IN-ValluvarNeural", "name": "Valluvar (Native Tamil Male)", "gender": "male"},
        ],
        "english": [
            {"id": "en-IN-NeerjaNeural", "name": "Neerja (Clear Indian English Female)", "gender": "female"},
            {"id": "en-US-JennyNeural", "name": "Jenny (Natural US English Female)", "gender": "female"},
        ],
        "defaults": DEFAULT_VOICES
    }

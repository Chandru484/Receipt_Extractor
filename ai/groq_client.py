import json
import logging
import re
from typing import Any, Dict, List, Optional, Union

from groq import Groq, APIError, RateLimitError, APITimeoutError

from core.config import settings
from ai.extraction_prompt import build_extraction_messages
from schemas.receipt_schema import ReceiptData

logger = logging.getLogger(__name__)


class GroqExtractionError(Exception):
    """Custom exception for errors during Groq API extraction."""
    pass


def get_groq_client(api_key: Optional[str] = None) -> Groq:
    """Instantiate and return the Groq SDK client for a specific or default API key."""
    target_key = (api_key or settings.GROQ_API_KEY).strip()
    if not target_key:
        raise GroqExtractionError("No Groq API key configured in .env file.")

    return Groq(
        api_key=target_key,
        timeout=settings.GROQ_TIMEOUT_SECONDS,
        max_retries=settings.GROQ_MAX_RETRIES
    )


def _sanitize_error(error_msg: str) -> str:
    """Sanitize error messages to ensure neither primary nor fallback API keys are ever leaked."""
    msg = str(error_msg)
    for key in [settings.GROQ_API_KEY, settings.GROQ_FALLBACK_API_KEY]:
        if key and key.strip() and key.strip() in msg:
            msg = msg.replace(key.strip(), "[REDACTED_API_KEY]")
    return msg


def _clean_json_response(raw_text: str) -> str:
    """Clean markdown code fences from JSON text if present."""
    text = raw_text.strip()
    # Strip opening ```json or ```
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    # Strip closing ```
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _repair_truncated_json(raw: str) -> str:
    """Attempt to close an incomplete JSON object caused by token truncation."""
    text = raw.strip()
    # Count unclosed braces / brackets
    depth_brace = text.count("{") - text.count("}")
    depth_bracket = text.count("[") - text.count("]")
    # Strip trailing comma before closing
    text = re.sub(r",\s*$", "", text)
    # Close any open string (truncated value)
    if text.count('"') % 2 == 1:
        text += '"'
    # Close open arrays then objects
    text += "]" * max(0, depth_bracket)
    text += "}" * max(0, depth_brace)
    return text


def _call_groq(client: Groq, model: str, messages: list, max_tokens: int) -> str:
    """Execute a single Groq chat completion and return the raw content string."""
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.0,
        max_completion_tokens=max_tokens,
        response_format={"type": "json_object"}
    )
    content = completion.choices[0].message.content or ""
    return content


def _extract_with_single_client(client: Groq, model: str, messages: list) -> ReceiptData:
    """Send extraction request to a specific Groq client instance and validate response."""
    tokens = settings.GROQ_MAX_COMPLETION_TOKENS
    try:
        raw = _call_groq(client, model=model, messages=messages, max_tokens=tokens)
    except RateLimitError as rle:
        # If rate limit exceeded because requested output tokens exceeded quota limit (e.g. OTPM)
        if "reduce max_tokens" in str(rle).lower() or "tokens" in str(rle).lower():
            reduced_tokens = max(1800, tokens // 2)
            logger.warning(f"Rate limit hit requesting {tokens} tokens. Retrying with reduced tokens: {reduced_tokens}")
            raw = _call_groq(client, model=model, messages=messages, max_tokens=reduced_tokens)
        else:
            raise

    if not raw:
        raise GroqExtractionError("Groq returned an empty response.")

    clean_text = _clean_json_response(raw)

    try:
        parsed_json = json.loads(clean_text)
    except json.JSONDecodeError:
        repaired = _repair_truncated_json(clean_text)
        try:
            parsed_json = json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise GroqExtractionError(f"Failed to parse Groq response as JSON: {exc}") from exc

    if not isinstance(parsed_json, dict):
        raise GroqExtractionError("Groq response is not a valid JSON dictionary.")

    return ReceiptData.model_validate(parsed_json)


def extract_receipt_with_groq(ocr_result: Union[Dict[str, Any], str]) -> ReceiptData:
    """
    Send OCR text to Groq and return validated ReceiptData.
    
    Resilience Strategy:
      1. Attempts extraction using the primary Groq API key and model.
      2. If the primary key encounters RateLimitError, APITimeoutError, or any API failure,
         automatically falls over to GROQ_FALLBACK_API_KEY.
      3. Repaired partial JSON is automatically recovered if truncation occurs.
    """
    if isinstance(ocr_result, str):
        ocr_result = {"full_text": ocr_result, "lines": []}
    ocr_text = ocr_result.get("full_text", "").strip()
    if not ocr_text:
        raise GroqExtractionError("OCR did not detect any readable text in the document.")

    messages = build_extraction_messages(ocr_result)

    # Build ordered list of Groq providers (primary first, then fallback)
    providers: List[Dict[str, str]] = []
    primary_key = settings.GROQ_API_KEY.strip()
    if primary_key:
        providers.append({
            "name": "primary",
            "api_key": primary_key,
            "model": settings.GROQ_MODEL
        })

    fallback_key = settings.GROQ_FALLBACK_API_KEY.strip()
    if fallback_key and fallback_key != primary_key:
        providers.append({
            "name": "fallback",
            "api_key": fallback_key,
            "model": settings.GROQ_FALLBACK_MODEL or settings.GROQ_MODEL
        })

    if not providers:
        raise GroqExtractionError("GROQ_API_KEY is not configured in .env file.")

    last_error: Optional[Exception] = None

    for idx, provider in enumerate(providers):
        name = provider["name"]
        api_key = provider["api_key"]
        model = provider["model"]

        try:
            client = get_groq_client(api_key=api_key)
            result = _extract_with_single_client(client, model=model, messages=messages)
            if idx > 0:
                logger.info(f"Successfully extracted receipt using fallback Groq API ({model}).")
            return result

        except Exception as exc:
            last_error = exc
            sanitized_msg = _sanitize_error(str(exc))
            if idx < len(providers) - 1:
                next_name = providers[idx + 1]["name"]
                logger.warning(
                    f"{name.capitalize()} Groq API failed ({sanitized_msg}). "
                    f"Failing over to {next_name} Groq API..."
                )
            else:
                logger.error(f"{name.capitalize()} Groq API also failed: {sanitized_msg}")

    # All providers exhausted
    err_detail = _sanitize_error(str(last_error)) if last_error else "Unknown error"
    if isinstance(last_error, RateLimitError):
        raise GroqExtractionError(
            f"Groq rate limit exceeded on all configured keys: {err_detail}"
        ) from last_error
    if isinstance(last_error, APITimeoutError):
        raise GroqExtractionError(
            f"Groq API request timed out after {settings.GROQ_TIMEOUT_SECONDS}s: {err_detail}"
        ) from last_error
    if isinstance(last_error, GroqExtractionError):
        raise last_error

    raise GroqExtractionError(f"Extraction failed across all Groq API keys: {err_detail}") from last_error

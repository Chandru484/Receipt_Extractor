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
        err_str = str(rle).lower()
        # If rate limit exceeded because requested output tokens exceeded quota limit (e.g. OTPM 1000 on Qwen)
        if "reduce max_tokens" in err_str or "tokens" in err_str or "otpm" in err_str:
            if "qwen" in model.lower():
                alt_model = "openai/gpt-oss-120b"
                logger.warning(
                    f"Model {model} hit OTPM rate limit. Auto-switching to higher quota model: {alt_model}..."
                )
                try:
                    raw = _call_groq(client, model=alt_model, messages=messages, max_tokens=tokens)
                except Exception:
                    raw = _call_groq(client, model="openai/gpt-oss-20b", messages=messages, max_tokens=tokens)
            else:
                reduced_tokens = 950 if "limit 1000" in err_str else max(900, tokens // 2)
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


def _split_multipage_ocr(ocr_result: Dict[str, Any]) -> List[tuple[int, Dict[str, Any]]]:
    """Split combined OCR text into independent, 1-indexed page payloads."""
    full_text = ocr_result.get("full_text", "")
    pattern = re.compile(r"^---\s*Page\s+(\d+)\s*---\s*$", re.MULTILINE | re.IGNORECASE)
    matches = list(pattern.finditer(full_text))
    if not matches:
        return [(1, ocr_result)]

    total_pages = ocr_result.get("total_pages", len(matches))
    pages: List[tuple[int, Dict[str, Any]]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(full_text)
        page_number = int(match.group(1))
        page_text = full_text[start:end].strip()
        if page_text:
            pages.append((page_number, {
                "full_text": page_text,
                "lines": [],
                "total_pages": total_pages,
            }))
    return pages


def _merge_receipt_pages(page_results: List[tuple[int, ReceiptData]]) -> ReceiptData:
    """Merge page extractions while retaining every item and its page number."""
    if not page_results:
        raise GroqExtractionError("OCR contained no extractable pages.")
    if len(page_results) == 1:
        page_number, receipt = page_results[0]
        for item in receipt.items:
            item.page = item.page or page_number
        return receipt

    merged = page_results[0][1].model_dump(exclude_none=True)
    items: List[Dict[str, Any]] = []
    extra_fields: Dict[str, Any] = {}

    for page_number, receipt in page_results:
        for item in receipt.items:
            item.page = item.page or page_number
            items.append(item.model_dump(exclude_none=True))
        if receipt.extra_fields:
            extra_fields.update(receipt.extra_fields)

        page_data = receipt.model_dump(exclude_none=True)
        for key, value in page_data.items():
            if key in {"items", "extra_fields", "bank_details"}:
                continue
            if value not in (None, "", [], {}):
                if key not in merged or merged[key] in (None, "", [], {}):
                    merged[key] = value

        if receipt.bank_details:
            merged["bank_details"] = receipt.bank_details.model_dump(exclude_none=True)

    merged["items"] = items
    if extra_fields:
        merged["extra_fields"] = extra_fields

    return ReceiptData.model_validate(merged)


def _extract_multipage_with_client(
    client: Groq,
    model: str,
    ocr_result: Dict[str, Any],
) -> ReceiptData:
    """Extract pages independently so response size does not truncate the bill."""
    page_payloads = _split_multipage_ocr(ocr_result)
    if len(page_payloads) <= 1:
        return _extract_with_single_client(
            client,
            model,
            build_extraction_messages(ocr_result),
        )

    page_results: List[tuple[int, ReceiptData]] = []
    all_lines = ocr_result.get("lines", [])
    for page_number, page_payload in page_payloads:
        if all_lines:
            page_payload["lines"] = [
                line for line in all_lines
                if line.get("page") == page_number
            ]
        receipt = _extract_with_single_client(
            client,
            model,
            build_extraction_messages(page_payload),
        )
        page_results.append((page_number, receipt))

    return _merge_receipt_pages(page_results)


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
            total_pages = ocr_result.get("total_pages", 1)
            if int(total_pages or 1) > 1:
                result = _extract_multipage_with_client(client, model, ocr_result)
            else:
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

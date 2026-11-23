import json
import logging
import os
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


def get_all_groq_api_keys() -> List[str]:
    """
    Retrieve all configured Groq API keys in priority order with deduplication.
    Supports:
      - GROQ_API_KEY
      - GROQ_API_KEYS (comma-separated list)
      - GROQ_FALLBACK_API_KEY
      - GROQ_FALLBACK_API_KEYS (comma-separated list)
      - Numbered env vars: GROQ_API_KEY_1..20, GROQ_FALLBACK_API_KEY_1..20
    """
    keys: List[str] = []
    seen = set()

    def _add(k: Optional[str]):
        if not k:
            return
        cleaned = str(k).strip()
        if cleaned and cleaned not in seen:
            seen.add(cleaned)
            keys.append(cleaned)

    # 1. Primary key
    _add(getattr(settings, "GROQ_API_KEY", ""))

    # 2. Comma-separated primary keys
    raw_keys = getattr(settings, "GROQ_API_KEYS", "") or ""
    for part in raw_keys.split(","):
        _add(part)

    # 3. Dedicated fallback key
    _add(getattr(settings, "GROQ_FALLBACK_API_KEY", ""))

    # 4. Comma-separated fallback keys
    raw_fb = getattr(settings, "GROQ_FALLBACK_API_KEYS", "") or ""
    for part in raw_fb.split(","):
        _add(part)

    # 5. Numbered environment variables (e.g. GROQ_API_KEY_1..20, GROQ_FALLBACK_API_KEY_1..20)
    for prefix in ("GROQ_API_KEY_", "GROQ_FALLBACK_API_KEY_"):
        for i in range(1, 21):
            env_val = os.environ.get(f"{prefix}{i}", "")
            if env_val:
                _add(env_val)

    return keys


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
    """Sanitize error messages to ensure no configured API keys are ever leaked."""
    msg = str(error_msg)
    candidate_keys = set(get_all_groq_api_keys())
    for attr in ["GROQ_API_KEY", "GROQ_FALLBACK_API_KEY", "GROQ_API_KEYS", "GROQ_FALLBACK_API_KEYS"]:
        val = getattr(settings, attr, "")
        if val:
            for item in str(val).split(","):
                item_s = item.strip()
                if item_s:
                    candidate_keys.add(item_s)

    for key in candidate_keys:
        if key and len(key) >= 5 and key in msg:
            msg = msg.replace(key, "[REDACTED_API_KEY]")
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
    # Strip opening/closing code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()

    # Balance unclosed quotes or drop dangling unclosed key
    if text.count('"') % 2 == 1:
        last_colon = text.rfind(':')
        last_quote = text.rfind('"')
        if last_colon != -1 and last_colon < last_quote:
            text += '"'
        else:
            text = text[:last_quote].rstrip()

    for _ in range(6):
        text = re.sub(r',\s*"[^"]*"\s*:\s*$', "", text)
        text = re.sub(r'{\s*"[^"]*"\s*:\s*$', "{", text)
        text = re.sub(r',\s*"[^"]*"\s*$', "", text)
        text = re.sub(r",\s*$", "", text).strip()

    stack = []
    in_str = False
    escape = False
    for ch in text:
        if ch == '"' and not escape:
            in_str = not in_str
        elif not in_str:
            if ch in '{[':
                stack.append(ch)
            elif ch == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif ch == ']' and stack and stack[-1] == '[':
                stack.pop()
        escape = (ch == '\\' and not escape)

    closing_map = {'{': '}', '[': ']'}
    closing = ''.join(closing_map[c] for c in reversed(stack))
    return text + closing


def _call_groq(client: Groq, model: str, messages: list, max_tokens: int, json_mode: bool = True) -> str:
    """Execute a single Groq chat completion and return the raw content string."""
    kwargs: Dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0.0,
        "max_completion_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    # For reasoning models (e.g. openai/gpt-oss-120b, openai/gpt-oss-20b), keep reasoning low so output is not exhausted
    if any(m in model.lower() for m in ["gpt-oss", "o1", "o3"]):
        kwargs["reasoning_effort"] = getattr(settings, "GROQ_REASONING_EFFORT", "low")

    completion = client.chat.completions.create(**kwargs)
    content = completion.choices[0].message.content or ""
    return content


def _extract_with_single_client(client: Groq, model: str, messages: list) -> ReceiptData:
    """Send extraction request to a specific Groq client instance and validate response."""
    tokens = min(settings.GROQ_MAX_COMPLETION_TOKENS, 2048)
    raw = None

    try:
        raw = _call_groq(client, model=model, messages=messages, max_tokens=tokens, json_mode=True)
    except Exception as exc:
        err_str = str(exc).lower()
        # 1. Handle JSON validation failure in Groq (e.g. code: json_validate_failed)
        if "json_validate_failed" in err_str or "failed to validate json" in err_str:
            logger.warning(f"Groq json_object validation failed on model {model}. Retrying in raw mode...")
            try:
                raw = _call_groq(client, model=model, messages=messages, max_tokens=tokens, json_mode=False)
            except Exception as e2:
                err_str = str(e2).lower()
                exc = e2

        # 2. Handle TPM / OTPM / Rate limit / Request too large
        if raw is None and any(w in err_str for w in ["limit 8000", "reduce max_tokens", "tokens", "otpm", "tpm", "413", "rate_limit_exceeded"]):
            reduced_tokens = 1800 if tokens > 1800 else 1200
            logger.warning(f"Token limit exceeded requesting {tokens} tokens on {model}. Retrying with {reduced_tokens} tokens...")
            try:
                raw = _call_groq(client, model=model, messages=messages, max_tokens=reduced_tokens, json_mode=True)
            except Exception:
                try:
                    alt_model = "openai/gpt-oss-20b" if "120b" in model else "openai/gpt-oss-120b"
                    raw = _call_groq(client, model=alt_model, messages=messages, max_tokens=reduced_tokens, json_mode=True)
                except Exception as e3:
                    exc = e3

        if raw is None:
            raise exc

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
                # For financial totals and tax summaries, the LAST page that contains them is authoritative
                if key in {"subtotal", "tax", "grand_total", "cgst", "sgst", "igst", "rounded_off", "amount_in_words", "hsn_tax_summary"}:
                    merged[key] = value
                elif str(value).strip().lower() not in {"unknown", "none", "null", ""}:
                    # Prefer valid non-unknown strings over missing or 'Unknown'
                    if key not in merged or str(merged.get(key, "")).strip().lower() in {"", "none", "null", "unknown"}:
                        merged[key] = value
                elif key not in merged or merged[key] in (None, "", [], {}):
                    merged[key] = value

        if receipt.bank_details:
            merged["bank_details"] = receipt.bank_details.model_dump(exclude_none=True)
        if receipt.hsn_tax_summary:
            merged["hsn_tax_summary"] = [h.model_dump(exclude_none=True) for h in receipt.hsn_tax_summary]

    merged["items"] = items
    if extra_fields:
        merged["extra_fields"] = extra_fields

    return ReceiptData.model_validate(merged)


def _extract_multipage_with_client(
    client: Groq,
    model: str,
    ocr_result: Dict[str, Any],
) -> ReceiptData:
    """Extract pages in parallel across available Groq keys so extraction finishes in seconds."""
    from concurrent.futures import ThreadPoolExecutor

    page_payloads = _split_multipage_ocr(ocr_result)
    if len(page_payloads) <= 1:
        return _extract_with_single_client(
            client,
            model,
            build_extraction_messages(ocr_result),
        )

    all_keys = get_all_groq_api_keys()
    all_lines = ocr_result.get("lines", [])

    def _process_page_item(idx: int, page_number: int, page_payload: Dict[str, Any]) -> tuple[int, ReceiptData]:
        if all_lines:
            page_payload["lines"] = [
                line for line in all_lines
                if line.get("page") == page_number
            ]
        # Distribute concurrent page requests across distinct Groq keys to prevent TPM rate limits
        if all_keys and len(all_keys) > 1:
            page_key = all_keys[idx % len(all_keys)]
            page_client = get_groq_client(api_key=page_key)
        else:
            page_client = client

        receipt = _extract_with_single_client(
            page_client,
            model,
            build_extraction_messages(page_payload),
        )
        return (page_number, receipt)

    max_workers = min(len(page_payloads), max(len(all_keys), 4))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_process_page_item, idx, p_num, p_payload)
            for idx, (p_num, p_payload) in enumerate(page_payloads)
        ]
        page_results = [f.result() for f in futures]

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

    # Build ordered list of Groq providers from all configured keys
    all_keys = get_all_groq_api_keys()
    providers: List[Dict[str, str]] = []
    for idx, key in enumerate(all_keys):
        if idx == 0:
            name = "primary"
            model = settings.GROQ_MODEL
        else:
            name = f"fallback_{idx}" if len(all_keys) > 2 else "fallback"
            model = settings.GROQ_FALLBACK_MODEL or settings.GROQ_MODEL
        providers.append({
            "name": name,
            "api_key": key,
            "model": model
        })

    if not providers:
        raise GroqExtractionError("No Groq API keys configured in .env file.")

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
                logger.info(f"Successfully extracted receipt using fallback Groq API key #{idx + 1} ({model}).")
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

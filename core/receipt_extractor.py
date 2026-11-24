from typing import Any, Dict
import numpy as np

from ai.groq_client import extract_receipt_with_groq
from extraction.validation import validate_and_reconcile_receipt, format_receipt_display
from processing.ocr_engine import extract_ocr_text
from processing.tamil_processor import normalize_tamil_text, normalize_ocr_lines
from schemas.receipt_schema import ReceiptData


def process_receipt(image: np.ndarray) -> Dict[str, Any]:
    """Execute end-to-end receipt extraction workflow."""
    ocr_result = extract_ocr_text(image)
    ocr_result["full_text"] = normalize_tamil_text(ocr_result.get("full_text", "").strip())
    ocr_result["lines"] = normalize_ocr_lines(ocr_result.get("lines", []))

    full_text = ocr_result.get("full_text", "").strip()
    if not full_text:
        raise ValueError("No readable text found in the uploaded receipt.")

    # Semantic extraction with Groq
    raw_receipt: ReceiptData = extract_receipt_with_groq(ocr_result)

    # Post-extraction validation and tax reconciliation
    validated_receipt, diagnostics = validate_and_reconcile_receipt(
        raw_receipt,
        ocr_text=full_text
    )

    # Generate user-friendly formatted display block
    formatted_display = format_receipt_display(validated_receipt)

    # Clean text lines without confidence or box coordinates
    clean_lines = [
        line["text"] if isinstance(line, dict) and "text" in line else str(line)
        for line in ocr_result.get("lines", [])
    ]

    return {
        "receipt": validated_receipt.model_dump(),
        "formatted_display": formatted_display,
        "ocr": {
            "full_text": ocr_result["full_text"],
            "lines": clean_lines,
            "line_count": len(clean_lines)
        },
        "diagnostics": diagnostics
    }


def process_receipt_from_text(full_text: str, combined_ocr: Dict[str, Any]) -> Dict[str, Any]:
    """Run Groq extraction on pre-assembled OCR text (used for multi-page PDFs).

    Args:
        full_text: Combined OCR text from all PDF pages (page-separated).
        combined_ocr: OCR metadata dict with 'full_text', 'lines', 'total_pages'.

    Returns:
        Same dict structure as process_receipt().
    """
    full_text = normalize_tamil_text(full_text)
    combined_ocr["full_text"] = full_text
    combined_ocr["lines"] = normalize_ocr_lines(combined_ocr.get("lines", []))

    if not full_text.strip():
        raise ValueError("No readable text found in the uploaded PDF.")

    raw_receipt: ReceiptData = extract_receipt_with_groq(combined_ocr)

    validated_receipt, diagnostics = validate_and_reconcile_receipt(
        raw_receipt,
        ocr_text=full_text
    )

    formatted_display = format_receipt_display(validated_receipt)

    clean_lines = [
        line["text"] if isinstance(line, dict) and "text" in line else str(line)
        for line in combined_ocr.get("lines", [])
    ]

    return {
        "receipt": validated_receipt.model_dump(),
        "formatted_display": formatted_display,
        "ocr": {
            "full_text": full_text,
            "lines": clean_lines,
            "line_count": len(clean_lines),
            "total_pages": combined_ocr.get("total_pages", 1)
        },
        "diagnostics": diagnostics
    }


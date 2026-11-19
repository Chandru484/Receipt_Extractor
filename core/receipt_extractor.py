from typing import Any, Dict
import numpy as np

from ai.groq_client import extract_receipt_with_groq
from extraction.validation import validate_and_reconcile_receipt, format_receipt_display
from processing.ocr_engine import extract_ocr_text
from schemas.receipt_schema import ReceiptData


def process_receipt(image: np.ndarray) -> Dict[str, Any]:
    """Execute end-to-end receipt extraction workflow."""
    ocr_result = extract_ocr_text(image)

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

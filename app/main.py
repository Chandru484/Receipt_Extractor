from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ai.groq_client import GroqExtractionError
from core.config import settings
from core.constants import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_PDF_EXTENSIONS, ALLOWED_EXTENSIONS
from core.receipt_extractor import process_receipt
from processing.image_processor import preprocess_image
from schemas.receipt_schema import ReceiptResponse
from storage.mongo_client import (
    save_extraction_to_mongodb,
    find_extraction_by_invoice_number,
    get_stored_extractions,
    get_stored_extraction_by_id,
    check_mongo_connection,
)

app = FastAPI(
    title="Receipt and Invoice Extraction API",
    description=(
        "Production-ready open-source bill and receipt extraction system using "
        "local PaddleOCR 3.x and Groq LLM semantic understanding."
    ),
    version="2.0.0"
)


@app.get("/", summary="Root status")
async def root():
    return {
        "message": "Receipt Extraction API is running"
    }


@app.get("/health", summary="Health check")
async def health():
    return {
        "status": "healthy",
        "ocr_engine": "PaddleOCR 3.x",
        "groq_model": settings.GROQ_MODEL,
        "groq_fallback_configured": bool(settings.GROQ_FALLBACK_API_KEY.strip()),
        "groq_fallback_model": settings.GROQ_FALLBACK_MODEL if settings.GROQ_FALLBACK_API_KEY.strip() else None,
        "mongodb": check_mongo_connection()
    }


@app.get("/receipts", summary="List stored receipt extractions from MongoDB")
async def list_stored_receipts(
    limit: int = Query(20, ge=1, le=100, description="Max records to return"),
    skip: int = Query(0, ge=0, description="Records to skip for pagination")
):
    """Retrieve previously extracted receipts stored in MongoDB."""
    records = await run_in_threadpool(get_stored_extractions, limit=limit, skip=skip)
    return {
        "count": len(records),
        "limit": limit,
        "skip": skip,
        "receipts": records
    }


@app.get("/receipts/by-invoice/{invoice_number}", summary="Get stored receipt by invoice number")
async def get_receipt_by_invoice(invoice_number: str):
    """Retrieve a stored receipt from MongoDB by its invoice number."""
    record = await run_in_threadpool(find_extraction_by_invoice_number, invoice_number)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stored receipt with invoice number '{invoice_number}' not found."
        )
    return record


@app.get("/receipts/{receipt_id}", summary="Get stored receipt extraction by ID")
async def get_stored_receipt(receipt_id: str):
    """Retrieve a single stored receipt extraction by its MongoDB ObjectId."""
    record = await run_in_threadpool(get_stored_extraction_by_id, receipt_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stored receipt with ID '{receipt_id}' not found."
        )
    return record


@app.post(
    "/extract",
    response_model=ReceiptResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Extract structured receipt data",
    description=(
        "Upload a receipt or invoice **image** (JPG, PNG, WebP, BMP) or **PDF** to extract "
        "unified structured JSON and OCR metadata in-memory and persist to MongoDB. "
        "For multi-page PDFs, all pages are OCR'd and results are merged into a single document."
    )
)
async def extract_receipt(
    file: UploadFile = File(..., description="Receipt or invoice file (JPG, PNG, WebP, BMP, PDF)")
):
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    is_pdf = extension in ALLOWED_PDF_EXTENSIONS
    is_image = extension in ALLOWED_IMAGE_EXTENSIONS

    if not is_pdf and not is_image:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unsupported format '{extension}'. "
                f"Allowed: {sorted(list(ALLOWED_IMAGE_EXTENSIONS | ALLOWED_PDF_EXTENSIONS))}"
            )
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    file_bytes = await file.read(max_bytes + 1)

    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
        )

    try:
        if is_pdf:
            extraction_result = await run_in_threadpool(_extract_from_pdf, file_bytes)
        else:
            processed_image = await run_in_threadpool(preprocess_image, file_bytes)
            extraction_result = await run_in_threadpool(process_receipt, processed_image)

        from schemas.receipt_schema import remove_none_values
        cleaned_data = remove_none_values(extraction_result["receipt"])
        response_payload = {
            "success": True,
            "message": "Receipt extracted successfully",
            "formatted_display": extraction_result.get("formatted_display"),
            "data": cleaned_data,
            "ocr": extraction_result["ocr"],
            "document_id": None
        }

        # Persist extracted JSON to MongoDB Receipt_Extraction collection
        # (automatically checks invoice_number and skips duplicate saving)
        doc_id = await run_in_threadpool(save_extraction_to_mongodb, response_payload)
        if doc_id:
            response_payload["document_id"] = doc_id
            if response_payload.get("is_duplicate"):
                response_payload["message"] = "Receipt extracted successfully (existing record found in database, duplicate save skipped)"

        return remove_none_values(response_payload)

    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)
        )

    except GroqExtractionError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc)
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during extraction: {str(exc)}"
        )


def _extract_from_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """Convert PDF pages to images and run OCR + LLM extraction on each page.

    For multi-page PDFs, full_text from all pages is concatenated and fed to the LLM
    once so that invoice headers on page 1 and line items on page 2 are unified.
    """
    from processing.pdf_processor import pdf_bytes_to_images
    from processing.ocr_engine import extract_ocr_text

    page_images = pdf_bytes_to_images(pdf_bytes, dpi=200)

    # OCR every page and concatenate full text with a page separator
    all_lines = []
    all_texts = []
    for page_num, page_img in enumerate(page_images, start=1):
        processed = preprocess_image_from_array(page_img)
        ocr_result = extract_ocr_text(processed)
        page_lines = ocr_result.get("lines", [])
        page_text = ocr_result.get("full_text", "")
        # Tag each line with the originating page number
        for line in page_lines:
            line["page"] = page_num
        all_lines.extend(page_lines)
        if page_text:
            all_texts.append(f"--- Page {page_num} ---\n{page_text}")

    combined_text = "\n\n".join(all_texts)
    combined_ocr = {"full_text": combined_text, "lines": all_lines, "total_pages": len(page_images)}

    # Run LLM extraction on the merged full text (more context = better accuracy)
    from core.receipt_extractor import process_receipt_from_text
    return process_receipt_from_text(combined_text, combined_ocr)


def preprocess_image_from_array(image_array) -> any:
    """Pass a numpy array directly (already decoded from PDF page)."""
    import numpy as np
    import cv2

    if image_array is None:
        raise ValueError("Empty image array from PDF page.")

    height, width = image_array.shape[:2]
    max_side = max(height, width)

    target_min = 900
    target_max = 1400

    if max_side < target_min:
        scale = float(target_min) / float(max_side)
        image_array = cv2.resize(
            image_array, (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_CUBIC
        )
    elif max_side > target_max:
        scale = float(target_max) / float(max_side)
        image_array = cv2.resize(
            image_array, (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA
        )

    return image_array

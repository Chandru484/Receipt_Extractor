from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, HTTPException, Query, UploadFile, status
from starlette.concurrency import run_in_threadpool

from ai.groq_client import GroqExtractionError
from core.config import settings
from core.constants import ALLOWED_IMAGE_EXTENSIONS
from core.receipt_extractor import process_receipt
from processing.image_processor import preprocess_image
from schemas.receipt_schema import ReceiptResponse
from storage.mongo_client import (
    save_extraction_to_mongodb,
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
    status_code=status.HTTP_200_OK,
    summary="Extract structured receipt data",
    description="Upload a receipt or invoice image to extract unified structured JSON and OCR metadata in-memory and persist in MongoDB."
)
async def extract_receipt(
    file: UploadFile = File(..., description="Receipt or invoice image file (JPG, PNG, WebP, BMP)")
):
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image format '{extension}'. Allowed: {sorted(list(ALLOWED_IMAGE_EXTENSIONS))}"
        )

    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    image_bytes = await file.read(max_bytes + 1)

    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty."
        )

    if len(image_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Uploaded file exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB} MB."
        )

    try:
        # In-memory image preprocessing
        processed_image = await run_in_threadpool(
            preprocess_image,
            image_bytes
        )

        # In-memory OCR and Groq extraction (zero file persistence)
        extraction_result = await run_in_threadpool(
            process_receipt,
            processed_image
        )

        response_payload = {
            "success": True,
            "message": "Receipt extracted successfully",
            "formatted_display": extraction_result.get("formatted_display"),
            "data": extraction_result["receipt"],
            "ocr": extraction_result["ocr"],
            "document_id": None
        }

        # Persist extracted JSON to MongoDB Receipt_Extraction collection
        doc_id = await run_in_threadpool(
            save_extraction_to_mongodb,
            response_payload
        )
        if doc_id:
            response_payload["document_id"] = doc_id

        return response_payload

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
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc)
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred during extraction: {str(exc)}"
        )

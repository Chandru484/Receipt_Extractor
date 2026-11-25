import hashlib
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, status, Request
from starlette.concurrency import run_in_threadpool
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from ai.chatbot import ask_chatbot
from ai.groq_client import GroqExtractionError, get_all_groq_api_keys
from core.config import settings
from core.constants import ALLOWED_IMAGE_EXTENSIONS, ALLOWED_PDF_EXTENSIONS, ALLOWED_EXTENSIONS
from core.receipt_extractor import process_receipt
from processing.image_processor import preprocess_image
from schemas.chat_schema import ChatRequest, ChatResponse
from schemas.receipt_schema import ReceiptResponse
from storage.mongo_client import (
    save_extraction_to_mongodb,
    find_extraction_by_file_hash,
    find_extraction_by_invoice_number,
    find_extraction_by_invoice_and_vendor,
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Integrate Universal AI Chatbot Platform routers
try:
    from universal_chatbot.backend.app.api.v1.chat_routes import router as chatbot_chat_router
    from universal_chatbot.backend.app.api.v1.document_routes import router as chatbot_doc_router
    from universal_chatbot.backend.app.api.v1.admin_routes import router as chatbot_admin_router
    from universal_chatbot.backend.app.api.v1.voice_routes import router as chatbot_voice_router
    from universal_chatbot.backend.app.api.v1.package_routes import router as chatbot_package_router

    app.include_router(chatbot_chat_router, prefix="/api/v1")
    app.include_router(chatbot_doc_router, prefix="/api/v1")
    app.include_router(chatbot_admin_router, prefix="/api/v1")
    app.include_router(chatbot_voice_router, prefix="/api/v1")
    app.include_router(chatbot_package_router, prefix="/api/v1")
except Exception as _cb_err:
    print(f"Warning: Universal Chatbot routers could not be loaded into app: {_cb_err}", flush=True)


@app.middleware("http")
async def measure_and_display_response_time(request: Request, call_next):
    """Log response time to terminal with high visibility and set X-Process-Time header."""
    start_time = time.perf_counter()
    response = await call_next(request)
    elapsed = time.perf_counter() - start_time
    ms = int(elapsed * 1000)

    # Set response header
    response.headers["X-Process-Time"] = f"{elapsed:.2f}s"

    # Display prominently in terminal
    path = request.url.path
    if path in ["/extract", "/chat/ask"]:
        print(
            f"\n"
            f"===============================================================\n"
            f"⏱️  [RESPONSE TIME] {request.method} {path} -> HTTP {response.status_code}\n"
            f"👉  Completed in: {elapsed:.2f}s ({ms} ms)\n"
            f"===============================================================\n",
            flush=True
        )
    else:
        print(f"⏱️  [{request.method}] {path} -> {response.status_code} in {elapsed:.2f}s ({ms} ms)", flush=True)

    return response


ROOT_DIR = Path(__file__).resolve().parent.parent
UI_PATH = ROOT_DIR / "ui.html"
WIDGET_PATH = ROOT_DIR / "universal_chatbot" / "widget" / "widget.js"


@app.get("/widget.js", include_in_schema=False)
async def serve_chatbot_widget():
    """Serve the embeddable Universal AI Chatbot script directly from this server."""
    if WIDGET_PATH.exists():
        return FileResponse(WIDGET_PATH, media_type="application/javascript")
    return JSONResponse(status_code=404, content={"detail": "Widget script not found"})


@app.get("/", summary="Root status and Web UI")
async def root(request: Request):
    accept = request.headers.get("accept", "")
    if "text/html" in accept and UI_PATH.exists():
        return FileResponse(UI_PATH, media_type="text/html")
    return {
        "message": "Receipt Extraction API is running"
    }


@app.get("/ui", response_class=HTMLResponse, include_in_schema=False)
@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def serve_web_ui():
    """Serve the Receipt Extractor Web Dashboard with embedded Chatbot."""
    if UI_PATH.exists():
        return FileResponse(UI_PATH, media_type="text/html")
    return HTMLResponse("<h1>Receipt Extractor UI</h1>", status_code=200)


@app.get("/health", summary="Health check")
async def health():
    keys = get_all_groq_api_keys()
    return {
        "status": "healthy",
        "ocr_engine": "PaddleOCR 3.x",
        "groq_model": settings.GROQ_MODEL,
        "groq_keys_count": len(keys),
        "groq_fallback_configured": len(keys) > 1,
        "groq_fallback_model": settings.GROQ_FALLBACK_MODEL if len(keys) > 1 else None,
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


@app.get(
    "/receipts/by-invoice/{invoice_number}",
    summary="Get stored receipt by invoice number and optional vendor"
)
async def get_receipt_by_invoice(
    invoice_number: str,
    vendor_name: Optional[str] = Query(
        None,
        description="Optional vendor or seller name to disambiguate receipts from different vendors"
    )
):
    """Retrieve a stored receipt from MongoDB by combining invoice number and optional vendor name."""
    record = await run_in_threadpool(find_extraction_by_invoice_and_vendor, invoice_number, vendor_name)
    if not record:
        vendor_clause = f" for vendor '{vendor_name}'" if vendor_name else ""
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Stored receipt with invoice number '{invoice_number}'{vendor_clause} not found."
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

@app.get("/chat", response_class=HTMLResponse, include_in_schema=False)
async def live_chat_page():
    with open("test_chat.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post(
    "/chat/ask",
    response_model=ChatResponse,
    summary="Ask project AI chatbot",
    description=(
        "Ask automated questions about the Receipt Extractor platform. "
        "Answers pre-trained FAQs, explains API parameters and features, "
        "and automatically flags when escalation to human support on Tawk.to is needed."
    )
)
async def chat_with_bot(request: ChatRequest):
    """Answer questions about the project using Groq LLM with Tawk.to human escalation."""
    return await run_in_threadpool(ask_chatbot, request)


@app.get("/extract", include_in_schema=False)
@app.get("/extract/", include_in_schema=False)
async def extract_receipt_get_info(request: Request):
    """Guide users who attempt to visit /extract with a GET request."""
    accept = request.headers.get("accept", "")
    if "text/html" in accept:
        return RedirectResponse(
            url="/docs#/default/extract_receipt_extract_post",
            status_code=status.HTTP_303_SEE_OTHER
        )
    return JSONResponse(
        status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
        content={
            "detail": "Method Not Allowed. The /extract endpoint requires an HTTP POST request with multipart/form-data containing a 'file' parameter.",
            "usage": {
                "method": "POST",
                "endpoint": "/extract",
                "content_type": "multipart/form-data",
                "form_field": "file (binary PDF or image file)",
                "interactive_docs": "/docs#/default/extract_receipt_extract_post"
            }
        }
    )


@app.post(
    "/extract",
    response_model=ReceiptResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract structured receipt data",
    description=(
        "Upload a receipt or invoice **image** (JPG, PNG, WebP, BMP) or **PDF** to extract "
        "unified structured JSON and OCR metadata in-memory and persist to MongoDB. "
        "Checks cache combining file SHA-256 hash and (invoice number + vendor/seller name)."
    )
)
@app.post("/extract/", response_model=ReceiptResponse, include_in_schema=False)
async def extract_receipt(
    file: UploadFile = File(..., description="Receipt or invoice file (JPG, PNG, WebP, BMP, PDF)"),
    invoice_number: Optional[str] = Form(None, description="Optional invoice/receipt number for fast combined cache lookup"),
    vendor_name: Optional[str] = Form(None, description="Optional vendor/seller name for combined cache lookup"),
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

    # Compute SHA-256 hash of the uploaded file for instant caching and deduplication
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    file_size_kb = len(file_bytes) / 1024.0

    try:
        # 1. Fast Cache Check: Level 1 (file SHA-256 hash)
        t_cache_start = time.perf_counter()
        cached_doc = await run_in_threadpool(find_extraction_by_file_hash, file_hash)

        # Level 2 Cache Check: Combined (invoice_number + vendor_name) if provided
        if not cached_doc and invoice_number:
            cached_doc = await run_in_threadpool(
                find_extraction_by_invoice_and_vendor,
                invoice_number,
                vendor_name
            )

        if cached_doc:
            cache_duration_ms = (time.perf_counter() - t_cache_start) * 1000.0
            cached_id = str(cached_doc.get("_id", ""))
            cached_data = cached_doc.get("data", {}) if isinstance(cached_doc.get("data"), dict) else {}
            inv_no = (
                cached_data.get("invoice_number")
                or cached_data.get("receipt_number")
                or cached_doc.get("invoice_number")
                or "N/A"
            )
            vendor = (
                cached_data.get("vendor_name")
                or cached_data.get("seller_name")
                or cached_doc.get("vendor_name")
                or "N/A"
            )
            total = cached_data.get("grand_total") or cached_doc.get("grand_total") or "N/A"

            # Print prominent terminal banner
            print("\n" + "=" * 70, flush=True)
            print(f"⚡ [CACHE HIT] Receipt already extracted! (Invoice: {inv_no} | Seller: {vendor})", flush=True)
            print(f"📄 File: {filename} ({file_size_kb:.1f} KB) | Doc ID: {cached_id}", flush=True)
            print(f"🏢 Seller: {vendor} | 🧾 Invoice: {inv_no} | Total: {total}", flush=True)
            print(f"⚡ Skipped OCR and LLM processing completely! Zero API calls used.", flush=True)
            print(f"👉 Returning cached extraction from MongoDB in {cache_duration_ms:.2f} ms", flush=True)
            print("=" * 70 + "\n", flush=True)

            return {
                "success": True,
                "message": "Receipt retrieved from database cache (already extracted)",
                "formatted_display": cached_doc.get("formatted_display"),
                "data": cached_data,
                "ocr": cached_doc.get("ocr") or {"full_text": "", "lines": [], "line_count": 0},
                "document_id": cached_id,
                "is_duplicate": True,
                "cache_hit": True
            }

        # 2. CACHE MISS: New receipt detected, run OCR and LLM extraction
        print("\n" + "=" * 70, flush=True)
        print(f"🔍 [CACHE MISS] New receipt file detected (SHA-256: {file_hash[:12]}...)", flush=True)
        print(f"📄 File: {filename} ({file_size_kb:.1f} KB)", flush=True)
        print(f"👉 Running extraction pipeline (OCR + Groq LLM)...", flush=True)
        print("=" * 70 + "\n", flush=True)

        t_start = time.perf_counter()
        if is_pdf:
            extraction_result = await run_in_threadpool(_extract_from_pdf, file_bytes)
        else:
            processed_image = await run_in_threadpool(preprocess_image, file_bytes)
            extraction_result = await run_in_threadpool(process_receipt, processed_image)

        elapsed_sec = round(time.perf_counter() - t_start, 2)
        extracted_receipt = extraction_result["receipt"]
        extracted_inv = (
            extracted_receipt.get("invoice_number")
            or extracted_receipt.get("receipt_number")
        )
        extracted_vendor = (
            extracted_receipt.get("vendor_name")
            or extracted_receipt.get("seller_name")
        )

        response_payload = {
            "success": True,
            "message": "Receipt extracted successfully",
            "formatted_display": extraction_result.get("formatted_display"),
            "data": extracted_receipt,
            "ocr": extraction_result["ocr"],
            "document_id": None,
            "cache_hit": False,
        }

        # Persist extracted JSON to MongoDB Receipt_Extraction collection
        # (checks file_hash AND combines invoice_number + vendor_name to prevent duplicate saving)
        doc_id = await run_in_threadpool(
            save_extraction_to_mongodb,
            response_payload,
            file_hash=file_hash,
            file_name=filename,
            vendor_name=extracted_vendor,
            invoice_number=extracted_inv
        )
        if doc_id:
            response_payload["document_id"] = doc_id
            if response_payload.get("is_duplicate"):
                response_payload["message"] = "Receipt extracted successfully (existing record updated in database)"

        print("\n" + "=" * 70, flush=True)
        print(f"✅ [EXTRACTION COMPLETE] Processed in {elapsed_sec}s", flush=True)
        print(f"💾 Persisted to MongoDB with Doc ID: {response_payload.get('document_id')}", flush=True)
        print(f"🏢 Seller: {extracted_vendor or 'N/A'} | 🧾 Invoice: {extracted_inv or 'N/A'}", flush=True)
        print("=" * 70 + "\n", flush=True)

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


def _extract_from_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    """Convert PDF pages to text and run extraction.

    For digitally-generated PDFs, extracts clean embedded text directly in milliseconds.
    For scanned/photographed PDFs, falls back to PaddleOCR image processing.
    """
    import pypdfium2
    from processing.pdf_processor import pdf_bytes_to_images
    from processing.ocr_engine import extract_ocr_text

    pdf = pypdfium2.PdfDocument(pdf_bytes)
    total_pages = len(pdf)
    all_lines = []
    all_texts = []

    from processing.tamil_processor import normalize_tamil_text

    page_texts = []
    total_digital_chars = 0
    for page_num, page in enumerate(pdf, start=1):
        text_page = page.get_textpage()
        page_text = normalize_tamil_text(text_page.get_text_range().strip())
        total_digital_chars += len(page_text)
        page_texts.append((page_num, page_text))

    has_digital_text = total_digital_chars >= 40

    if has_digital_text:
        for page_num, page_text in page_texts:
            for l in page_text.splitlines():
                l_str = l.strip()
                if l_str:
                    all_lines.append({"text": l_str, "page": page_num})
            if page_text:
                all_texts.append(f"--- Page {page_num} ---\n{page_text}")
    else:
        page_images = pdf_bytes_to_images(pdf_bytes, dpi=200)
        for page_num, page_img in enumerate(page_images, start=1):
            processed = preprocess_image_from_array(page_img)
            ocr_result = extract_ocr_text(processed)
            page_lines = ocr_result.get("lines", [])
            page_text = ocr_result.get("full_text", "")
            for line in page_lines:
                line["page"] = page_num
            all_lines.extend(page_lines)
            if page_text:
                all_texts.append(f"--- Page {page_num} ---\n{page_text}")

    combined_text = "\n\n".join(all_texts)
    combined_ocr = {"full_text": combined_text, "lines": all_lines, "total_pages": total_pages}

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

import json
import os
from io import BytesIO
from pathlib import Path
from PIL import Image
import numpy as np

os.environ["GRADIO_SSR_MODE"] = "false"
os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"

# Patch Gradio schema parser bug when dealing with Pydantic v2 additionalProperties: bool
try:
    import gradio_client.utils

    _orig_get_type = gradio_client.utils.get_type
    def _safe_get_type(schema):
        if isinstance(schema, bool):
            return "bool"
        return _orig_get_type(schema)
    gradio_client.utils.get_type = _safe_get_type

    _orig_schema = gradio_client.utils._json_schema_to_python_type
    def _safe_schema(schema, defs=None):
        if isinstance(schema, bool):
            return "bool"
        return _orig_schema(schema, defs)
    gradio_client.utils._json_schema_to_python_type = _safe_schema
except Exception:
    pass

try:
    import spaces
    gpu_decorator = spaces.GPU
except Exception:
    def gpu_decorator(fn=None, **kwargs):
        if callable(fn):
            return fn
        return lambda f: f

import gradio as gr
from app.main import app as fastapi_app
from core.receipt_extractor import process_receipt, process_receipt_from_text
from processing.image_processor import preprocess_image
from storage.mongo_client import save_extraction_to_mongodb


@gpu_decorator
def gradio_extract(file):
    """Handle image or PDF upload from Gradio File component."""
    if file is None:
        return "Please upload an image or PDF.", "{}"

    file_path = Path(file.name) if hasattr(file, "name") else Path(str(file))
    extension = file_path.suffix.lower()

    try:
        with open(file_path, "rb") as f:
            file_bytes = f.read()
    except Exception as e:
        return f"Could not read uploaded file: {e}", "{}"

    try:
        if extension == ".pdf":
            from processing.pdf_processor import pdf_bytes_to_images
            from processing.ocr_engine import extract_ocr_text

            page_images = pdf_bytes_to_images(file_bytes, dpi=200)
            all_lines = []
            all_texts = []
            for page_num, page_img in enumerate(page_images, start=1):
                from app.main import preprocess_image_from_array
                processed = preprocess_image_from_array(page_img)
                ocr_result = extract_ocr_text(processed)
                for line in ocr_result.get("lines", []):
                    line["page"] = page_num
                all_lines.extend(ocr_result.get("lines", []))
                pg_text = ocr_result.get("full_text", "")
                if pg_text:
                    all_texts.append(f"--- Page {page_num} ---\n{pg_text}")

            combined_text = "\n\n".join(all_texts)
            combined_ocr = {
                "full_text": combined_text,
                "lines": all_lines,
                "total_pages": len(page_images)
            }
            result = process_receipt_from_text(combined_text, combined_ocr)
        else:
            # Image path
            processed = preprocess_image(file_bytes)
            result = process_receipt(processed)

        response_payload = {
            "success": True,
            "message": "Receipt extracted successfully",
            "formatted_display": result.get("formatted_display"),
            "data": result["receipt"],
            "ocr": result["ocr"],
            "document_id": None
        }

        doc_id = save_extraction_to_mongodb(response_payload)
        if doc_id:
            response_payload["document_id"] = doc_id

        summary = result.get("formatted_display", "")
        if doc_id:
            if response_payload.get("is_duplicate"):
                summary += f"\n\n[Existing record found in MongoDB Atlas with ID: {doc_id} (duplicate save skipped)]"
            else:
                summary += f"\n\n[Saved in MongoDB Atlas with ID: {doc_id}]"

        return summary, json.dumps(response_payload, indent=2)

    except Exception as e:
        return f"Extraction failed: {e}", "{}"


with gr.Blocks(title="Receipt & Invoice Extractor API") as demo:
    gr.Markdown("# 🧾 Production Receipt & Invoice Extractor API")
    gr.Markdown(
        "Upload any **receipt / invoice image** (JPG, PNG, WebP, BMP) or **PDF** to extract "
        "structured line items, taxes, bank details, and persist to MongoDB Atlas.\n\n"
        "- **Interactive API Docs (Swagger)**: [/docs](/docs)\n"
        "- **Health Check Endpoint**: [/health](/health)\n"
        "- **Query Stored Receipts**: [/receipts](/receipts)"
    )
    with gr.Row():
        with gr.Column():
            input_file = gr.File(
                label="Upload Receipt / Invoice (Image or PDF)",
                file_types=["image", ".pdf"],
                type="filepath"
            )
            btn = gr.Button("Extract Receipt", variant="primary")
        with gr.Column():
            output_display = gr.Textbox(label="Formatted Summary", lines=16)
            output_json = gr.Code(label="Extracted JSON", language="json")

    btn.click(gradio_extract, inputs=[input_file], outputs=[output_display, output_json])

# Register all FastAPI routes (/extract, /health, /receipts) into Gradio's internal FastAPI app
demo.app.include_router(fastapi_app.router)

# Enable interactive Swagger UI (/docs), ReDoc (/redoc), and OpenAPI schema (/openapi.json)
demo.app.docs_url = "/docs"
demo.app.redoc_url = "/redoc"
demo.app.openapi_url = "/openapi.json"
demo.app.title = "Receipt & Invoice Extraction API"
demo.app.description = fastapi_app.description
demo.app.version = fastapi_app.version
demo.app.setup()

app = demo.app

# Launch native Gradio server (demo.launch() automatically detects Hugging Face Spaces)
if __name__ == "__main__":
    demo.launch(app_kwargs={"docs_url": "/docs", "redoc_url": "/redoc", "openapi_url": "/openapi.json"})


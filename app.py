import json
import os
from io import BytesIO
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
from core.receipt_extractor import process_receipt
from processing.image_processor import preprocess_image
from storage.mongo_client import save_extraction_to_mongodb


@gpu_decorator
def gradio_extract(image):
    if image is None:
        return "Please upload an image.", "{}"

    buf = BytesIO()
    if isinstance(image, Image.Image):
        image.convert("RGB").save(buf, format="JPEG")
        img_bytes = buf.getvalue()
    elif isinstance(image, np.ndarray):
        import cv2
        _, encoded = cv2.imencode(".jpg", cv2.cvtColor(image, cv2.COLOR_RGB2BGR))
        img_bytes = encoded.tobytes()
    else:
        return "Unsupported image type.", "{}"

    processed = preprocess_image(img_bytes)
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
        summary += f"\n\n[Saved in MongoDB Atlas with ID: {doc_id}]"

    return summary, json.dumps(response_payload, indent=2)


with gr.Blocks(title="Receipt & Invoice Extractor API") as demo:
    gr.Markdown("# 🧾 Production Receipt & Invoice Extractor API")
    gr.Markdown(
        "Upload any bill or receipt to extract structured line items, taxes, bank details, and persist to MongoDB Atlas.\n\n"
        "- **Interactive API Docs (Swagger)**: [/docs](/docs)\n"
        "- **Health Check Endpoint**: [/health](/health)\n"
        "- **Query Stored Receipts**: [/receipts](/receipts)"
    )
    with gr.Row():
        with gr.Column():
            input_image = gr.Image(type="pil", label="Upload Receipt / Invoice Image")
            btn = gr.Button("Extract Receipt", variant="primary")
        with gr.Column():
            output_display = gr.Textbox(label="Formatted Summary", lines=16)
            output_json = gr.Code(label="Extracted JSON", language="json")

    btn.click(gradio_extract, inputs=[input_image], outputs=[output_display, output_json])

# Register all FastAPI routes (/extract, /health, /receipts, /docs) into Gradio's internal FastAPI app
demo.app.include_router(fastapi_app.router)
app = demo.app

# Launch native Gradio server (demo.launch() automatically detects Hugging Face Spaces)
if __name__ == "__main__":
    demo.launch()

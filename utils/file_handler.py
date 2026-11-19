import json
from pathlib import Path
from uuid import uuid4

from core.constants import ALLOWED_IMAGE_EXTENSIONS

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def validate_image_extension(filename: str) -> bool:
    """Check if the filename has an allowed image extension."""
    if not filename:
        return False
    extension = Path(filename).suffix.lower()
    return extension in ALLOWED_IMAGE_EXTENSIONS


def save_uploaded_image(image_bytes: bytes, filename: str) -> Path:
    """Save raw uploaded image bytes to disk."""
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError("Unsupported image extension.")

    unique_filename = f"{uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / unique_filename
    file_path.write_bytes(image_bytes)
    return file_path


def save_extraction_result(data: dict) -> Path:
    """Save extraction result JSON to disk."""
    output_path = OUTPUT_DIR / f"{uuid4().hex}.json"
    output_path.write_text(
        json.dumps(data, indent=4, ensure_ascii=False),
        encoding="utf-8"
    )
    return output_path

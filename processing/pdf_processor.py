"""
PDF to image conversion for receipt/invoice PDF files.

Converts each page of a PDF into a high-resolution numpy array for OCR processing.
All conversion is done fully in-memory — no temporary files are written to disk.
"""
import os
import shutil
from io import BytesIO
from typing import List, Optional

import numpy as np


def _find_poppler_path() -> Optional[str]:
    """Locate the poppler bin directory on the current platform.

    - On Linux/macOS (HF Spaces, Docker): poppler-utils is on PATH, return None so
      pdf2image auto-detects it.
    - On Windows (local dev): winget installs poppler under a known WinGet packages path.
      We locate pdftoppm.exe there if it is not already on PATH.
    """
    # Already on PATH — no extra config needed
    if shutil.which("pdftoppm"):
        return None

    # Windows: check the common winget install location
    if os.name == "nt":
        local_app = os.environ.get("LOCALAPPDATA", "")
        winget_base = os.path.join(local_app, "Microsoft", "WinGet", "Packages")
        if os.path.isdir(winget_base):
            for entry in os.listdir(winget_base):
                if entry.lower().startswith("oschwartz10612.poppler"):
                    candidate = os.path.join(winget_base, entry)
                    # Walk one level deeper to find Library/bin
                    for root, dirs, files in os.walk(candidate):
                        if "pdftoppm.exe" in files:
                            return root

    return None


def pdf_bytes_to_images(pdf_bytes: bytes, dpi: int = 200) -> List[np.ndarray]:
    """Convert PDF bytes to a list of numpy image arrays (one per page).

    Args:
        pdf_bytes: Raw bytes of the PDF file.
        dpi: Rendering resolution. 200 DPI gives ~1600-2000px wide pages
             which is ideal for PaddleOCR without excessive memory use.

    Returns:
        List of BGR numpy arrays, one per page.

    Raises:
        ValueError: If the PDF is empty, corrupted, or has zero pages.
        ImportError: If pdf2image / poppler is not installed.
    """
    try:
        from pdf2image import convert_from_bytes
    except ImportError as exc:
        raise ImportError(
            "pdf2image is required for PDF support. "
            "Install it with: pip install pdf2image\n"
            "Also ensure poppler-utils is installed on the system."
        ) from exc

    if not pdf_bytes:
        raise ValueError("PDF data is empty.")

    poppler_path = _find_poppler_path()

    pil_pages = convert_from_bytes(
        pdf_bytes,
        dpi=dpi,
        fmt="jpeg",
        thread_count=1,          # single-threaded to avoid fork issues in Docker
        use_pdftocairo=True,     # cairo renderer — better quality, faster
        strict=False,            # tolerate slightly malformed PDFs
        poppler_path=poppler_path,  # None → auto-detect on Linux; explicit path on Windows
    )

    if not pil_pages:
        raise ValueError("PDF contains no renderable pages.")

    images: List[np.ndarray] = []
    for page in pil_pages:
        # Convert PIL RGB → BGR numpy array for OpenCV / PaddleOCR
        rgb_array = np.array(page.convert("RGB"))
        bgr_array = rgb_array[:, :, ::-1].copy()
        images.append(bgr_array)

    return images

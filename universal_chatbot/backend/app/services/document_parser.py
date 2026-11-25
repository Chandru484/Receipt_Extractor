import os
import io
import re
import zipfile
import xml.etree.ElementTree as ET
from functools import lru_cache
from typing import List, Dict, Any

try:
    import pypdfium2 as pdfium
    HAS_PDFIUM = True
except ImportError:
    HAS_PDFIUM = False

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}
TEXT_EXTENSIONS = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".xml", ".html", ".htm",
    ".py", ".js", ".ts", ".css", ".log", ".yaml", ".yml", ".ini", ".sql"
}


@lru_cache(maxsize=1)
def _get_lazy_ocr():
    """Lazy-load PaddleOCR 3.x only when an image or scanned PDF is uploaded."""
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from paddlex.inference.models.runners.paddle_static import runner
        for m in ["PP-OCRv6_small_det", "PP-OCRv6_small_rec", "PP-OCRv6_medium_det", "PP-OCRv6_medium_rec"]:
            if m not in runner.MKLDNN_BLOCKLIST:
                runner.MKLDNN_BLOCKLIST.append(m)
    except Exception:
        pass

    from paddleocr import PaddleOCR
    return PaddleOCR(
        lang="en",
        device="cpu",
        text_detection_model_name="PP-OCRv6_small_det",
        text_recognition_model_name="PP-OCRv6_small_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
    )


def _ocr_np_image(img_array) -> str:
    """Run OCR on a numpy RGB/BGR image array and return extracted text."""
    try:
        ocr = _get_lazy_ocr()
        result = ocr.predict(img_array)
        lines: List[str] = []
        if result:
            for item in result:
                if isinstance(item, dict) and "rec_texts" in item:
                    lines.extend([t for t in item["rec_texts"] if t and t.strip()])
                elif hasattr(item, "get") and item.get("rec_texts"):
                    lines.extend([t for t in item["rec_texts"] if t and t.strip()])
        return "\n".join(lines)
    except Exception:
        return ""


def _extract_docx(file_bytes: bytes) -> str:
    """Extract text from .docx using built-in zipfile + XML parser (zero external deps)."""
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        if "word/document.xml" not in zf.namelist():
            return ""
        xml_bytes = zf.read("word/document.xml")
    root = ET.fromstring(xml_bytes)
    paragraphs: List[str] = []
    for p in root.iter():
        if p.tag.endswith("}p"):
            texts = [t.text for t in p.iter() if t.tag.endswith("}t") and t.text]
            if texts:
                paragraphs.append("".join(texts))
    return "\n\n".join(paragraphs)


def _extract_pptx(file_bytes: bytes) -> str:
    """Extract slide text from .pptx using built-in zipfile + XML parser."""
    slides_text: List[str] = []
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        slide_files = sorted(
            [n for n in zf.namelist() if n.startswith("ppt/slides/slide") and n.endswith(".xml")]
        )
        for idx, sfile in enumerate(slide_files, start=1):
            root = ET.fromstring(zf.read(sfile))
            texts = [t.text.strip() for t in root.iter() if t.tag.endswith("}t") and t.text and t.text.strip()]
            if texts:
                slides_text.append(f"--- [Slide {idx}] ---\n" + "\n".join(texts))
    return "\n\n".join(slides_text)


def _extract_xlsx(file_bytes: bytes) -> str:
    """Extract cell text from .xlsx using built-in zipfile + XML parser."""
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            ss_root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for si in ss_root.iter():
                if si.tag.endswith("}si"):
                    parts = [t.text for t in si.iter() if t.tag.endswith("}t") and t.text]
                    shared_strings.append("".join(parts))

        sheet_files = sorted(
            [n for n in zf.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")]
        )
        all_sheets: List[str] = []
        for idx, sfile in enumerate(sheet_files, start=1):
            root = ET.fromstring(zf.read(sfile))
            rows_text: List[str] = []
            for row in root.iter():
                if row.tag.endswith("}row"):
                    row_vals: List[str] = []
                    for cell in row:
                        if cell.tag.endswith("}c"):
                            cell_type = cell.attrib.get("t", "")
                            val_elem = next((ch for ch in cell if ch.tag.endswith("}v")), None)
                            if val_elem is not None and val_elem.text is not None:
                                val = val_elem.text
                                if cell_type == "s" and val.isdigit() and int(val) < len(shared_strings):
                                    val = shared_strings[int(val)]
                                row_vals.append(val)
                            else:
                                # Inline string
                                inline_t = [t.text for t in cell.iter() if t.tag.endswith("}t") and t.text]
                                if inline_t:
                                    row_vals.append("".join(inline_t))
                    if row_vals:
                        rows_text.append(" | ".join(row_vals))
            if rows_text:
                all_sheets.append(f"--- [Sheet {idx}] ---\n" + "\n".join(rows_text))
        return "\n\n".join(all_sheets)


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract clean text content from any uploaded file (PDF, DOCX, XLSX, PPTX, images, text/CSV/JSON)."""
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        if not HAS_PDFIUM:
            raise RuntimeError("PDF extraction library (pypdfium2) is not installed.")
        pdf = pdfium.PdfDocument(file_bytes)
        text_parts: List[str] = []
        for page_idx, page in enumerate(pdf):
            textpage = page.get_textpage()
            page_text = textpage.get_text_range()
            if page_text and page_text.strip():
                text_parts.append(f"--- [Page {page_idx + 1}] ---\n" + page_text.strip())

        combined = "\n\n".join(text_parts)
        # Fallback to OCR if PDF is scanned / image-based
        if len(combined.strip()) < 30 and len(pdf) > 0:
            import numpy as np
            ocr_parts: List[str] = []
            for page_idx, page in enumerate(pdf):
                bitmap = page.render(scale=2.0)
                pil_img = bitmap.to_pil()
                ocr_text = _ocr_np_image(np.array(pil_img))
                if ocr_text.strip():
                    ocr_parts.append(f"--- [Page {page_idx + 1} (OCR)] ---\n" + ocr_text.strip())
            if ocr_parts:
                return "\n\n".join(ocr_parts)
        return combined

    elif ext in IMAGE_EXTENSIONS:
        from PIL import Image
        import numpy as np
        pil_img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        return _ocr_np_image(np.array(pil_img))

    elif ext == ".docx":
        return _extract_docx(file_bytes)

    elif ext == ".xlsx":
        return _extract_xlsx(file_bytes)

    elif ext == ".pptx":
        return _extract_pptx(file_bytes)

    elif ext in TEXT_EXTENSIONS:
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1", errors="replace")

    else:
        # Generic fallback: decode readable UTF-8/Latin-1 text
        try:
            decoded = file_bytes.decode("utf-8")
            return decoded
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1", errors="ignore")


def chunk_text(
    text: str,
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> List[Dict[str, Any]]:
    """
    Split text into overlapping semantic chunks preserving paragraphs, lines, and sentences.
    Returns list of dicts with 'chunk_index', 'text', 'char_count'.
    """
    if not text or not text.strip():
        return []

    cleaned = re.sub(r"\r\n", "\n", text.strip())
    # Split by double newline (paragraphs) first
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]

    # Break down oversized paragraphs (e.g. CSVs, logs, single-newline docs) by single newline
    segments: List[str] = []
    for p in paragraphs:
        if len(p) <= chunk_size:
            segments.append(p)
        else:
            lines = [ln.strip() for ln in p.split("\n") if ln.strip()]
            for ln in lines:
                if len(ln) <= chunk_size:
                    segments.append(ln)
                else:
                    # Split long line into sentences or fixed-size slices
                    sentences = re.split(r"(?<=[.!?])\s+", ln)
                    for s in sentences:
                        if len(s) <= chunk_size:
                            segments.append(s)
                        else:
                            for start in range(0, len(s), chunk_size - chunk_overlap):
                                segments.append(s[start:start + chunk_size])

    chunks: List[Dict[str, Any]] = []
    current_chunk: List[str] = []
    current_length = 0
    chunk_idx = 0

    for seg in segments:
        seg_len = len(seg)
        if current_length + seg_len + 2 <= chunk_size:
            current_chunk.append(seg)
            current_length += seg_len + 2
        else:
            if current_chunk:
                chunk_str = "\n".join(current_chunk)
                chunks.append({
                    "chunk_index": chunk_idx,
                    "text": chunk_str,
                    "char_count": len(chunk_str),
                })
                chunk_idx += 1

                if len(current_chunk) > 1 and len(current_chunk[-1]) <= chunk_overlap:
                    current_chunk = [current_chunk[-1], seg]
                    current_length = len(current_chunk[0]) + seg_len + 2
                else:
                    current_chunk = [seg]
                    current_length = seg_len
            else:
                chunks.append({
                    "chunk_index": chunk_idx,
                    "text": seg,
                    "char_count": seg_len,
                })
                chunk_idx += 1
                current_chunk = []
                current_length = 0

    if current_chunk:
        chunk_str = "\n".join(current_chunk).strip()
        if chunk_str:
            chunks.append({
                "chunk_index": chunk_idx,
                "text": chunk_str,
                "char_count": len(chunk_str),
            })

    return chunks

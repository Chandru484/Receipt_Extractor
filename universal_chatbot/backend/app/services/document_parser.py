import os
import io
import re
from typing import List, Dict, Any, Optional

try:
    import pypdfium2 as pdfium
    HAS_PDFIUM = True
except ImportError:
    HAS_PDFIUM = False


def extract_text_from_bytes(file_bytes: bytes, filename: str) -> str:
    """Extract clean text content from uploaded file bytes based on file extension."""
    ext = os.path.splitext(filename)[1].lower()

    if ext == ".pdf":
        if not HAS_PDFIUM:
            raise RuntimeError("PDF extraction library (pypdfium2) is not installed.")
        pdf = pdfium.PdfDocument(file_bytes)
        text_parts = []
        for page_idx, page in enumerate(pdf):
            textpage = page.get_textpage()
            page_text = textpage.get_text_range()
            if page_text and page_text.strip():
                text_parts.append(f"--- [Page {page_idx + 1}] ---\n" + page_text.strip())
        return "\n\n".join(text_parts)

    elif ext in [".txt", ".md", ".csv", ".json", ".xml", ".html", ".py", ".js"]:
        # Attempt UTF-8 decoding, fallback to latin-1
        try:
            return file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return file_bytes.decode("latin-1", errors="replace")

    else:
        # Fallback binary text extraction for unsupported types
        try:
            return file_bytes.decode("utf-8", errors="ignore")
        except Exception:
            return ""


def chunk_text(
    text: str,
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> List[Dict[str, Any]]:
    """
    Split text into overlapping semantic chunks preserving paragraphs and sentences.
    Returns list of dicts with 'chunk_index', 'text', 'char_count'.
    """
    if not text or not text.strip():
        return []

    cleaned = re.sub(r"\r\n", "\n", text.strip())
    # Split by double newline (paragraphs) first
    paragraphs = [p.strip() for p in cleaned.split("\n\n") if p.strip()]

    chunks: List[Dict[str, Any]] = []
    current_chunk = []
    current_length = 0
    chunk_idx = 0

    for para in paragraphs:
        para_len = len(para)
        if current_length + para_len + 2 <= chunk_size:
            current_chunk.append(para)
            current_length += para_len + 2
        else:
            if current_chunk:
                chunk_str = "\n\n".join(current_chunk)
                chunks.append({
                    "chunk_index": chunk_idx,
                    "text": chunk_str,
                    "char_count": len(chunk_str),
                })
                chunk_idx += 1
                
                # Overlap: keep last paragraph if it fits
                if len(current_chunk) > 1 and len(current_chunk[-1]) <= chunk_overlap:
                    current_chunk = [current_chunk[-1], para]
                    current_length = len(current_chunk[0]) + para_len + 2
                else:
                    current_chunk = [para]
                    current_length = para_len
            else:
                # Single paragraph exceeds chunk_size, split by sentences or hard break
                sentences = re.split(r"(?<=[.!?])\s+", para)
                for sentence in sentences:
                    s_len = len(sentence)
                    if current_length + s_len + 1 <= chunk_size:
                        current_chunk.append(sentence)
                        current_length += s_len + 1
                    else:
                        if current_chunk:
                            chunk_str = " ".join(current_chunk)
                            chunks.append({
                                "chunk_index": chunk_idx,
                                "text": chunk_str,
                                "char_count": len(chunk_str),
                            })
                            chunk_idx += 1
                        current_chunk = [sentence]
                        current_length = s_len

    if current_chunk:
        chunk_str = "\n\n".join(current_chunk) if "\n\n" in "\n\n".join(current_chunk) else " ".join(current_chunk)
        if chunk_str.strip():
            chunks.append({
                "chunk_index": chunk_idx,
                "text": chunk_str.strip(),
                "char_count": len(chunk_str.strip()),
            })

    return chunks

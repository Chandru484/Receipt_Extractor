import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from core.config import BASE_DIR, settings

# Ensure environment variables are configured before PaddleOCR imports
if os.environ.get("SPACE_ID") or not os.access(str(BASE_DIR), os.W_OK):
    cache_base = Path("/tmp/.cache")
else:
    cache_base = BASE_DIR / ".cache"

os.environ.setdefault("PADDLE_PDX_CACHE_HOME", str(cache_base / "paddlex"))
os.environ.setdefault("PADDLE_HOME", str(cache_base / "paddle"))
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

# Monkey-patch MKLDNN_BLOCKLIST for Windows CPU compatibility in PaddlePaddle 3.4.0
try:
    from paddlex.inference.models.runners.paddle_static import runner
    for model_name in [
        "PP-OCRv6_small_det",
        "PP-OCRv6_small_rec",
        "PP-OCRv6_medium_det",
        "PP-OCRv6_medium_rec"
    ]:
        if model_name not in runner.MKLDNN_BLOCKLIST:
            runner.MKLDNN_BLOCKLIST.append(model_name)
except Exception:
    pass

from paddleocr import PaddleOCR


@lru_cache(maxsize=1)
def get_ocr_engine() -> PaddleOCR:
    """Initialize and cache the high-speed, lightweight PaddleOCR 3.x engine singleton."""
    return PaddleOCR(
        lang=settings.OCR_LANGUAGE,
        device="cpu",
        text_detection_model_name="PP-OCRv6_small_det",
        text_recognition_model_name="PP-OCRv6_small_rec",
        text_recognition_batch_size=16,
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False
    )


def _to_python_native(val: Any) -> Any:
    """Recursively convert numpy arrays and scalars to Python native types."""
    if hasattr(val, "tolist"):
        return val.tolist()
    if isinstance(val, (np.floating, float)):
        return round(float(val), 4)
    if isinstance(val, (np.integer, int)):
        return int(val)
    if isinstance(val, list):
        return [_to_python_native(item) for item in val]
    return val


def _get_box_geometry(box: Any) -> tuple[float, float, float, float]:
    """Calculate (ymin, ymax, xmin, xmax) from bounding box points."""
    if not box:
        return (0.0, 0.0, 0.0, 0.0)
    arr = np.array(box)
    if arr.ndim == 2 and arr.shape[0] >= 4:
        # 4 points: [[x1, y1], [x2, y2], [x3, y3], [x4, y4]]
        xmin = float(np.min(arr[:, 0]))
        xmax = float(np.max(arr[:, 0]))
        ymin = float(np.min(arr[:, 1]))
        ymax = float(np.max(arr[:, 1]))
        return (ymin, ymax, xmin, xmax)
    elif arr.size == 4:
        # [xmin, ymin, xmax, ymax]
        flat = arr.flatten()
        return (float(flat[1]), float(flat[3]), float(flat[0]), float(flat[2]))
    return (0.0, 0.0, 0.0, 0.0)


def sort_lines_reading_order(raw_lines: List[Dict[str, Any]], y_tolerance_ratio: float = 0.35) -> List[Dict[str, Any]]:
    """Sort detected text lines in natural reading order (top-to-bottom, left-to-right).
    
    Receipts frequently have tabular columns (e.g. Description, Qty, Rate, Total) that
    must be read on the same horizontal line even if their y-coordinates differ slightly.
    Also avoids merging cells that overlap horizontally (i.e. from the same column across rows).
    """
    if not raw_lines:
        return []

    boxes_with_geo = []
    for item in raw_lines:
        ymin, ymax, xmin, xmax = _get_box_geometry(item.get("box"))
        height = max(1.0, ymax - ymin)
        y_center = (ymin + ymax) / 2.0
        boxes_with_geo.append({
            "data": item,
            "ymin": ymin,
            "ymax": ymax,
            "xmin": xmin,
            "xmax": xmax,
            "height": height,
            "y_center": y_center
        })

    # Sort initially by y_center
    boxes_with_geo.sort(key=lambda b: b["y_center"])

    # Group into horizontal text lines
    lines: List[List[Dict[str, Any]]] = []
    for b in boxes_with_geo:
        placed = False
        for line in lines:
            avg_y = sum(item["y_center"] for item in line) / len(line)
            avg_h = sum(item["height"] for item in line) / len(line)
            tolerance = avg_h * y_tolerance_ratio

            if abs(b["y_center"] - avg_y) <= tolerance:
                # Disallow x-overlap: if line already has a box overlapping horizontally, don't merge
                has_x_overlap = False
                for item in line:
                    x_overlap = max(0.0, min(b["xmax"], item["xmax"]) - max(b["xmin"], item["xmin"]))
                    min_w = min(b["xmax"] - b["xmin"], item["xmax"] - item["xmin"])
                    if min_w > 0 and (x_overlap / min_w) > 0.4:
                        has_x_overlap = True
                        break
                if not has_x_overlap:
                    line.append(b)
                    placed = True
                    break
        if not placed:
            lines.append([b])

    # Sort lines by average y, and within each line sort by xmin (left to right)
    lines.sort(key=lambda l: sum(item["y_center"] for item in l) / len(l))
    sorted_items = []
    for line in lines:
        line.sort(key=lambda item: item["xmin"])
        sorted_items.extend(item["data"] for item in line)

    return sorted_items


def extract_ocr_text(image: np.ndarray) -> Dict[str, Any]:
    """Run PaddleOCR on the preprocessed image and extract structured text, boxes, and confidence."""
    ocr = get_ocr_engine()
    results = ocr.predict(image)

    if not results:
        return {
            "full_text": "",
            "lines": []
        }

    raw_lines: List[Dict[str, Any]] = []

    for result in results:
        result_data = result.json
        if callable(result_data):
            result_data = result_data()

        if not isinstance(result_data, dict):
            continue

        result_data = result_data.get("res", result_data)
        texts = result_data.get("rec_texts", [])
        scores = result_data.get("rec_scores", [])
        boxes = result_data.get("rec_boxes", [])

        for index, text in enumerate(texts):
            text_str = str(text).strip()
            if not text_str:
                continue

            score = (
                float(scores[index])
                if index < len(scores) and scores[index] is not None
                else None
            )

            box = (
                _to_python_native(boxes[index])
                if index < len(boxes) and boxes[index] is not None
                else None
            )

            raw_lines.append({
                "text": text_str,
                "confidence": round(score, 4) if score is not None else None,
                "box": box
            })

    # Sort lines according to natural document reading order
    ordered_lines = sort_lines_reading_order(raw_lines)

    # Compose full text
    full_text = "\n".join(item["text"] for item in ordered_lines)

    return {
        "full_text": full_text,
        "lines": ordered_lines
    }

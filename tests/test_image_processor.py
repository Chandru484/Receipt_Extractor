import cv2
import numpy as np
import pytest
from processing.image_processor import preprocess_image


def test_preprocess_image_empty_bytes():
    with pytest.raises(ValueError, match="Image data is empty"):
        preprocess_image(b"")


def test_preprocess_image_invalid_bytes():
    with pytest.raises(ValueError, match="Could not decode"):
        preprocess_image(b"not a valid image byte sequence")


def test_preprocess_image_valid_synthetic_image():
    # Create synthetic test image (100x100 white square with black text)
    img = np.ones((100, 100, 3), dtype=np.uint8) * 255
    cv2.putText(img, "TEST", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), 2)
    success, encoded = cv2.imencode(".png", img)
    assert success

    processed = preprocess_image(encoded.tobytes())
    assert isinstance(processed, np.ndarray)
    # Scaled to minimum optimal OCR dimension (900)
    assert max(processed.shape[:2]) == 900


def test_preprocess_image_resizes_oversized():
    # Create oversized image (3000 x 1500)
    img = np.ones((3000, 1500, 3), dtype=np.uint8) * 255
    success, encoded = cv2.imencode(".jpg", img)
    assert success

    processed = preprocess_image(encoded.tobytes())
    # Max dimension should be 1400
    assert max(processed.shape[:2]) == 1400
    assert processed.shape[0] == 1400
    assert processed.shape[1] == 700

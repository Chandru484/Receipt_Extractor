import cv2
import numpy as np


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """Preprocess uploaded receipt image for OCR.
    
    Decodes the image and scales it to an optimal resolution (1800-2500px on the longest side)
    to ensure high-precision OCR text detection of small fonts, GSTINs, codes, and line items.
    """
    if not image_bytes:
        raise ValueError("Image data is empty.")

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError("Invalid or corrupted image file. Could not decode.")

    height, width = image.shape[:2]
    max_side = max(height, width)

    # Optimal resolution range for fast, high-accuracy CPU OCR
    target_min = 900
    target_max = 1400

    if max_side < target_min:
        scale = float(target_min) / float(max_side)
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    elif max_side > target_max:
        scale = float(target_max) / float(max_side)
        new_width = max(1, int(width * scale))
        new_height = max(1, int(height * scale))
        image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_AREA)

    return image

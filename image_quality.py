from pathlib import Path

import cv2
import numpy as np


SHARPNESS_REFERENCE = 500.0
TARGET_RESOLUTION_PIXELS = 1280 * 720


def calculate_image_quality(image_path: str | Path) -> float:
    """Return a simple, explainable image score between 0 and 10."""
    image_bytes = np.fromfile(str(image_path), dtype=np.uint8)
    try:
        image = cv2.imdecode(image_bytes, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"OpenCV could not read image: {image_path}")

        height, width = image.shape[:2]
        grayscale = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        laplacian_variance = cv2.Laplacian(grayscale, cv2.CV_64F).var()
        sharpness_score = min(laplacian_variance / SHARPNESS_REFERENCE * 10, 10)

        brightness = float(np.mean(grayscale))
        brightness_score = max(0.0, 10 - abs(brightness - 127.5) / 127.5 * 10)

        resolution_score = min((width * height) / TARGET_RESOLUTION_PIXELS * 10, 10)

        final_score = (
            sharpness_score * 0.60
            + brightness_score * 0.25
            + resolution_score * 0.15
        )
    except cv2.error as error:
        raise ValueError(f"OpenCV could not score image: {image_path}") from error

    return round(max(0.0, min(final_score, 10.0)), 1)

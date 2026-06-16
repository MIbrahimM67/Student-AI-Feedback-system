"""
GradeWise visual supplement.

Tesseract OCR is intentionally disabled for this project. Diagram, design, and
image submissions should go through the vision model path in
services/ocr_service.py, where the model describes the visual structure instead
of flattening it into raw OCR text.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def ocr_code_region(image_bytes: bytes) -> str | None:
    """OCR is disabled. Use the vision evidence extractor instead."""
    logger.info("Literal OCR supplement is disabled; using vision extraction upstream.")
    return None


def is_likely_code_screenshot(image_bytes: bytes, page_text: str | None = None) -> bool:
    """Return False because OCR-based code screenshot handling is disabled."""
    return False

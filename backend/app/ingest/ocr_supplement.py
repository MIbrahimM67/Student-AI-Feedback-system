"""
GradeWise — OCR Supplement for literal code/terminal grading.

Used ONLY when a page region is flagged as containing code or terminal output
where exact, literal character matching is required for grading.
"""
from __future__ import annotations

import logging
from io import BytesIO

from PIL import Image
import pytesseract

logger = logging.getLogger(__name__)


def ocr_code_region(image_bytes: bytes) -> str | None:
    """
    Run Tesseract OCR on an image buffer.
    Returns the extracted text, or None if extraction fails/is empty.
    """
    try:
        img = Image.open(BytesIO(image_bytes))
        # Optional: pre-processing could go here (grayscale, binarization)
        # but since this is rendered from PyMuPDF, it's usually clean enough.
        text = pytesseract.image_to_string(img, config="--psm 6")
        text = text.strip()
        if text:
            return text
        return None
    except Exception as e:
        logger.warning("OCR supplement failed: %s", e)
        return None


def is_likely_code_screenshot(image_bytes: bytes, page_text: str | None = None) -> bool:
    """
    Heuristic to detect if an image is a code/terminal screenshot.
    This is a placeholder for a more sophisticated classifier if needed.

    Currently: returns False unless triggered externally by assignment metadata.
    """
    # DECISION: We rely on external flagging (e.g. assignment type == 'coding')
    # rather than blind heuristics to decide when to incur OCR latency.
    return False

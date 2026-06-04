"""
GradeWise — Document Structure and Size Estimation.

Used by the router to decide if a document can fit in context (Tier 0)
or if it has enough hierarchical structure to support tree navigation (Tier 1).
"""
from __future__ import annotations

import logging
from pathlib import Path

import fitz  # PyMuPDF

from app.grading.types import DocumentPayload
from app.grading import config

logger = logging.getLogger(__name__)


def estimate_tokens(payload: DocumentPayload) -> int:
    """
    Estimate the total token cost of this document.
    NOTE: Since grader.py operates in text-only mode (extracted_text from pages),
    we only count text tokens — not image tokens. Image token costs (800/page) are
    only relevant if the model receives base64-encoded images, which it currently does not.
    """
    if payload.text_only and payload.plain_text:
        return len(payload.plain_text) // 4  # rough heuristic: 4 chars ≈ 1 token

    text_tokens = 0
    if payload.pages:
        for page in payload.pages:
            if page.extracted_text:
                text_tokens += len(page.extracted_text) // 4
            if page.code_ocr_text:
                text_tokens += len(page.code_ocr_text) // 4

    # NOTE: image_tokens intentionally omitted — grader sends text only.
    # Re-enable this line only if base64 image payloads are restored:
    # image_tokens = len(payload.pages) * config.TOKENS_PER_PAGE_IMAGE

    return text_tokens


def detect_structure(path: str) -> bool:
    """
    Detect if a document has hierarchical structure (e.g. Table of Contents).
    Currently supports PDFs via PyMuPDF.

    Returns True if a TOC/Bookmarks exist, False otherwise.
    """
    suffix = Path(path).suffix.lower()

    if suffix != ".pdf":
        return False

    try:
        doc = fitz.open(path)
        toc = doc.get_toc()
        doc.close()
        # A TOC exists and has at least one entry
        return bool(toc and len(toc) > 0)
    except Exception as e:
        logger.warning("Failed to detect structure for %s: %s", path, e)
        return False

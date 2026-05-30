"""
GradeWise — Document Ingestion: Render, Don't OCR.

Converts any supported document into a DocumentPayload whose pages are
rendered as PNG images (so embedded screenshots and diagrams are visible
to the model). OCR is a supplement only for code/terminal regions.

Routing by file type:
  DOCX  → convert to PDF via LibreOffice headless → treat as PDF
  PDF   → render each page to PNG via PyMuPDF @ config.RENDER_DPI
  image → single PageImage, no OCR
  text/md → text_only=True, plain_text set, pages=[]
"""
from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path

import fitz  # PyMuPDF

from app.grading.types import DocumentPayload, PageImage
from app.grading import config
from app.ingest.docx_to_pdf import convert as docx_to_pdf
from app.router.structure import estimate_tokens, detect_structure

logger = logging.getLogger(__name__)

_TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".rst"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff"}
_PDF_EXTENSIONS = {".pdf"}
_DOCX_EXTENSIONS = {".docx", ".doc"}


def ingest(path: str) -> DocumentPayload:
    """
    Ingest a document and return a DocumentPayload.

    GUARDRAIL: OCR is NOT invoked on the default path. Call
    ocr_supplement.ocr_code_region() separately only when the
    code-screenshot flag is set.
    """
    suffix = Path(path).suffix.lower()

    if suffix in _TEXT_EXTENSIONS:
        return _ingest_text(path)

    if suffix in _IMAGE_EXTENSIONS:
        return _ingest_image(path)

    if suffix in _DOCX_EXTENSIONS:
        pdf_path = docx_to_pdf(path)
        return _ingest_pdf(pdf_path, original_path=path)

    if suffix in _PDF_EXTENSIONS:
        return _ingest_pdf(path)

    if suffix == ".zip":
        return _ingest_zip(path)

    # Unknown type: attempt PDF rendering, fall back to text extraction
    logger.warning("Unknown file type %s — attempting PDF rendering.", suffix)
    try:
        return _ingest_pdf(path)
    except Exception:
        logger.error("Could not ingest %s as PDF.", path)
        raise ValueError(f"Unsupported file type: {suffix}")


# Extensions we want to extract from student ZIPs as readable text
_CODE_EXTENSIONS = {
    ".py", ".cpp", ".c", ".java", ".js", ".ts", ".cs", ".go", ".rb", ".php",
    ".swift", ".kt", ".rs", ".sh", ".html", ".css", ".sql", ".txt", ".md",
    ".h", ".hpp", ".cc", ".r", ".m", ".pl", ".scala", ".dart"
}


def _ingest_zip(path: str) -> DocumentPayload:
    """
    Extract all readable code/text files from a student ZIP submission.
    Concatenates them with filename headers so the grader sees the actual code.
    """
    parts = []
    try:
        with zipfile.ZipFile(path, "r") as zf:
            # Sort so files come in a predictable order
            names = sorted(zf.namelist())
            for name in names:
                # Skip directories and hidden/meta files
                if name.endswith("/") or name.startswith("__MACOSX") or "/.git/" in name:
                    continue
                ext = Path(name).suffix.lower()
                if ext not in _CODE_EXTENSIONS:
                    continue
                try:
                    content = zf.read(name).decode("utf-8", errors="replace").strip()
                    if content:
                        parts.append(f"=== FILE: {name} ===\n{content}")
                except Exception as e:
                    logger.warning("Could not read %s from ZIP: %s", name, e)
    except zipfile.BadZipFile:
        logger.warning("Bad ZIP file at %s — treating as empty submission", path)

    if not parts:
        logger.warning("ZIP %s had no readable code files — submission will be empty", path)
        text = "[No readable source code files found in submission ZIP]"
    else:
        text = "\n\n".join(parts)
        logger.info("ZIP %s: extracted %d file(s), ~%d chars", path, len(parts), len(text))

    est_tokens = len(text) // 4
    return DocumentPayload(
        source_path=path,
        pages=[],
        est_tokens=est_tokens,
        has_structure=False,
        text_only=True,
        plain_text=text,
    )


def _ingest_text(path: str) -> DocumentPayload:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()
    # Rough token estimate: 1 token ≈ 4 characters
    est_tokens = len(text) // 4
    return DocumentPayload(
        source_path=path,
        pages=[],
        est_tokens=est_tokens,
        has_structure=False,
        text_only=True,
        plain_text=text,
    )


def _ingest_image(path: str) -> DocumentPayload:
    with open(path, "rb") as f:
        image_bytes = f.read()

    # Determine MIME type from extension
    ext = Path(path).suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tiff": "image/tiff",
    }
    mime = mime_map.get(ext, "image/png")

    page = PageImage(
        page_number=1,
        image_bytes=image_bytes,
        mime_type=mime,
    )
    return DocumentPayload(
        source_path=path,
        pages=[page],
        est_tokens=config.TOKENS_PER_PAGE_IMAGE,
        has_structure=False,
        text_only=False,
    )


def _ingest_pdf(path: str, original_path: str | None = None) -> DocumentPayload:
    """
    Render each page of a PDF to a PNG image at RENDER_DPI.
    Optionally also extracts text for text-dense pages.
    """
    doc = fitz.open(path)
    pages: list[PageImage] = []

    for page_num in range(len(doc)):
        page = doc.load_page(page_num)

        # Render to PNG — this preserves embedded images, diagrams, screenshots
        mat = fitz.Matrix(config.RENDER_DPI / 72, config.RENDER_DPI / 72)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        image_bytes = pix.tobytes("png")

        # Optionally extract text for text-dense pages (not used by model — for
        # structure detection and token estimation only)
        extracted_text: str | None = None
        try:
            text = page.get_text("text").strip()
            if text:
                extracted_text = text
        except Exception:
            pass

        pages.append(PageImage(
            page_number=page_num + 1,
            image_bytes=image_bytes,
            mime_type="image/png",
            extracted_text=extracted_text,
        ))

    doc.close()

    has_structure = detect_structure(path)

    # Build a DocumentPayload and estimate tokens
    payload = DocumentPayload(
        source_path=original_path or path,
        pages=pages,
        est_tokens=0,  # filled below
        has_structure=has_structure,
        text_only=False,
    )
    payload.est_tokens = estimate_tokens(payload)
    return payload

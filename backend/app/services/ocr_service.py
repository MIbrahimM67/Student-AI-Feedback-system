"""
GradeWise v3 — OCR service.

Tier 1: PyMuPDF (typed PDFs) → pure text, no AI needed.
Tier 2: Tesseract OCR (clear scans / printed handwriting).
Tier 3: Vision model via Gradient (messy cursive — optional, set GRADIENT_VISION_OCR_MODEL).

No simulation mode. No mock text. Real extraction only.
"""
from __future__ import annotations

import logging
import os
import tempfile

logger = logging.getLogger(__name__)


class OCRService:

    async def extract_text(self, file_path: str, filename: str) -> str:
        """
        Extract text from a file. Returns clean UTF-8 text.
        Raises ValueError if no readable text could be extracted.
        """
        ext = os.path.splitext(filename)[1].lower()

        # ---- Tier 1: PyMuPDF — typed/digital PDFs ---------------------------
        if ext == ".pdf":
            text = self._pymupdf_extract(file_path)
            if text.strip():
                logger.info("PyMuPDF extracted %d chars from %s", len(text), filename)
                return text
            # PDF is scanned (no embedded text) — fall through to OCR

        # ---- Plain text / code files ----------------------------------------
        if ext in (".txt", ".py", ".java", ".cpp", ".c", ".js", ".ts", ".cs", ".go"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        # ---- DOCX -----------------------------------------------------------
        if ext in (".docx", ".doc"):
            return self._docx_extract(file_path)

        # ---- Tier 2: Tesseract OCR (images + scanned PDFs) ------------------
        text = await self._tesseract_extract(file_path, ext)
        if text.strip():
            return text

        # ---- Tier 3: Vision model (optional) --------------------------------
        from app.config import settings
        if settings.GRADIENT_VISION_OCR_MODEL:
            text = await self._vision_model_extract(file_path, filename)
            if text.strip():
                return text

        raise ValueError(
            f"Could not extract readable text from '{filename}'. "
            "Try uploading a clearer scan or a typed PDF."
        )

    # ---- Tier 1: PyMuPDF ----------------------------------------------------

    def _pymupdf_extract(self, file_path: str) -> str:
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(file_path)
            pages = [page.get_text() for page in doc]
            doc.close()
            return "\n\n".join(pages)
        except Exception as e:
            logger.warning("PyMuPDF failed: %s", e)
            return ""

    # ---- DOCX ---------------------------------------------------------------

    def _docx_extract(self, file_path: str) -> str:
        try:
            from docx import Document
            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.warning("python-docx extraction failed: %s", e)
            return ""

    # ---- Tier 2: Tesseract --------------------------------------------------

    async def _tesseract_extract(self, file_path: str, ext: str) -> str:
        try:
            import pytesseract
            from PIL import Image

            if ext in (".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"):
                image = Image.open(file_path)
                text = pytesseract.image_to_string(image)
                logger.info("Tesseract extracted %d chars", len(text))
                return text

            if ext == ".pdf":
                # Convert PDF pages to images then OCR
                try:
                    from pdf2image import convert_from_path
                    images = convert_from_path(file_path)
                    parts = [pytesseract.image_to_string(img) for img in images]
                    return "\n\n".join(parts)
                except ImportError:
                    logger.warning("pdf2image not installed — cannot OCR scanned PDF pages")
                    return ""

        except ImportError:
            logger.warning("pytesseract not installed")
        except Exception as e:
            logger.warning("Tesseract OCR failed: %s", e)
        return ""

    # ---- Tier 3: Vision model -----------------------------------------------

    async def _vision_model_extract(self, file_path: str, filename: str) -> str:
        """
        Call the DigitalOcean vision model to transcribe handwriting.
        Only runs if GRADIENT_VISION_OCR_MODEL is set in config.
        """
        try:
            import base64
            from app.config import settings
            from app.services.llm_provider import build_llm_from_env, ChatMessage

            with open(file_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            llm = build_llm_from_env()
            resp = await llm.chat(
                messages=[
                    ChatMessage(
                        role="user",
                        content=[
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                            {
                                "type": "text",
                                "text": (
                                    "Transcribe ALL handwritten text in this image exactly as written. "
                                    "Preserve paragraph breaks. Output only the transcribed text."
                                ),
                            },
                        ],
                    )
                ],
                model=settings.GRADIENT_VISION_OCR_MODEL,
                temperature=0.0,
                max_tokens=4096,
            )
            logger.info("Vision model transcribed %d chars from %s", len(resp.text), filename)
            return resp.text
        except Exception as e:
            logger.error("Vision model OCR failed: %s", e)
            return ""


# Global instance
ocr_service = OCRService()

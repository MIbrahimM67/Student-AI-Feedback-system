"""
GradeWise visual extraction service.

This intentionally does not use Tesseract. For this project, uploaded images are
often diagrams, flowcharts, UI designs, architecture sketches, or other visual
artifacts where OCR alone loses the grading signal.

Flow:
  - Typed PDFs: extract embedded text with PyMuPDF, then optionally add visual
    page descriptions for diagrams/screenshots.
  - Images and scanned PDFs: send the rendered image/page to a vision model.
  - DOCX/code/text: use deterministic text extraction.
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp"}
TEXT_EXTENSIONS = {".txt", ".py", ".java", ".cpp", ".cc", ".cxx", ".c", ".js", ".ts", ".cs", ".go"}


class OCRService:
    async def extract_text(
        self,
        file_path: str,
        filename: str,
        *,
        skip_vision: bool = False,
    ) -> str:
        """
        Return grading-ready textual evidence from the uploaded file.

        For visual files, this is a structured visual analysis from the vision
        model, not OCR text.

        Args:
            skip_vision: When True, bypass the vision model entirely and use
                only embedded text extraction (PyMuPDF).  Pass True for coding
                or plain-text submissions where vision adds no value.
        """
        ext = os.path.splitext(filename)[1].lower()

        if ext in TEXT_EXTENSIONS:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        if ext in (".docx", ".doc"):
            return self._docx_extract(file_path)

        if ext in IMAGE_EXTENSIONS:
            if skip_vision:
                raise ValueError(
                    f"File '{filename}' is an image but vision extraction is disabled for "
                    "this submission type. Re-submit as a PDF or enable visual extraction."
                )
            from app.config import settings
            if not settings.VISUAL_EXTRACTION_ENABLED:
                raise ValueError(
                    "Image/diagram grading needs a running vision model. "
                    "Configure DEDICATED_VISION_MODEL or GRADIENT_VISION_OCR_MODEL and set "
                    "VISUAL_EXTRACTION_ENABLED=true."
                )
            return await self._vision_model_extract(file_path, filename)

        if ext == ".pdf":
            return await self._pdf_extract(file_path, filename, skip_vision=skip_vision)

        raise ValueError(
            f"Could not extract readable grading evidence from '{filename}'. "
            "Supported inputs: text/code, DOCX, PDF, and images."
        )

    def _pymupdf_extract(self, file_path: str) -> str:
        try:
            import fitz

            doc = fitz.open(file_path)
            pages = [page.get_text() for page in doc]
            doc.close()
            return "\n\n".join(pages).strip()
        except Exception as e:
            logger.warning("PyMuPDF text extraction failed: %s", e)
            return ""

    def _docx_extract(self, file_path: str) -> str:
        try:
            from docx import Document

            doc = Document(file_path)
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            return "\n\n".join(paragraphs)
        except Exception as e:
            logger.warning("python-docx extraction failed: %s", e)
            return ""

    async def _pdf_extract(
        self, file_path: str, filename: str, *, skip_vision: bool = False
    ) -> str:
        from app.config import settings

        embedded_text = self._pymupdf_extract(file_path)
        if skip_vision or not settings.VISUAL_EXTRACTION_ENABLED:
            if embedded_text:
                if skip_vision:
                    logger.info(
                        "Vision skipped (coding/text submission) — PyMuPDF extracted %d chars from %s",
                        len(embedded_text),
                        filename,
                    )
                else:
                    logger.info("PyMuPDF extracted %d chars from %s", len(embedded_text), filename)
                return embedded_text
            raise ValueError(f"PDF '{filename}' has no embedded text and visual extraction is disabled.")

        visual_parts = await self._vision_extract_pdf_pages(file_path, filename)
        if embedded_text and visual_parts:
            return (
                "=== EMBEDDED PDF TEXT ===\n"
                f"{embedded_text}\n\n"
                "=== VISUAL PAGE ANALYSIS ===\n"
                f"{visual_parts}"
            )
        if visual_parts:
            return visual_parts
        if embedded_text:
            return embedded_text

        raise ValueError(f"Could not extract text or visual evidence from '{filename}'.")

    async def _vision_extract_pdf_pages(self, file_path: str, filename: str) -> str:
        from app.config import settings

        try:
            import fitz

            doc = fitz.open(file_path)
            total_pages = len(doc)
            page_indices = self._select_pdf_pages_for_vision(
                doc,
                settings.VISUAL_EXTRACTION_MAX_PDF_PAGES,
            )
            parts: list[str] = []

            for idx in page_indices:
                page = doc.load_page(idx)
                pix = page.get_pixmap(matrix=fitz.Matrix(1.8, 1.8), alpha=False)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    tmp.write(pix.tobytes("png"))
                    tmp_path = tmp.name
                try:
                    try:
                        analysis = await self._vision_model_extract(tmp_path, f"{filename} page {idx + 1}")
                        if analysis.strip():
                            parts.append(f"--- Page {idx + 1} visual analysis ---\n{analysis}")
                    except Exception as page_error:
                        if settings.DOCUMENT_DEMO:
                            raise  # Missing visual evidence must not become grading input.
                        logger.warning(
                            "Vision extraction failed for %s page %d: %s",
                            filename,
                            idx + 1,
                            page_error,
                        )
                        parts.append(
                            f"--- Page {idx + 1} visual analysis unavailable ---\n"
                            f"Vision extraction failed for this page: {page_error}"
                        )
                finally:
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)

                if settings.VISUAL_EXTRACTION_PAGE_DELAY_SECONDS > 0 and idx != page_indices[-1]:
                    await asyncio.sleep(settings.VISUAL_EXTRACTION_PAGE_DELAY_SECONDS)

            doc.close()

            if 0 < settings.VISUAL_EXTRACTION_MAX_PDF_PAGES < total_pages and len(page_indices) < total_pages:
                selected = ", ".join(str(idx + 1) for idx in page_indices)
                parts.append(
                    f"[Visual analysis scanned all {total_pages} PDF pages and selected pages "
                    f"{selected or 'none'} for vision based on image/vector/scan signals. "
                    "Set VISUAL_EXTRACTION_MAX_PDF_PAGES=0 to visually analyze every page.]"
                )

            return "\n\n".join(parts)
        except Exception as e:
            logger.warning("PDF visual extraction failed for %s: %s", filename, e)
            if settings.DOCUMENT_DEMO:
                raise
            return ""

    def _select_pdf_pages_for_vision(self, doc, max_pages: int) -> list[int]:
        total_pages = len(doc)
        if total_pages == 0:
            return []
        if max_pages <= 0 or total_pages <= max_pages:
            return list(range(total_pages))

        scored_pages: list[tuple[float, int]] = []
        for idx in range(total_pages):
            page = doc.load_page(idx)
            try:
                text = page.get_text("text").strip()
            except Exception:
                text = ""
            try:
                image_count = len(page.get_images(full=True))
            except Exception:
                image_count = 0
            try:
                blocks = page.get_text("dict").get("blocks", [])
                image_blocks = sum(1 for block in blocks if block.get("type") == 1)
            except Exception:
                image_blocks = 0
            try:
                drawing_count = len(page.get_drawings())
            except Exception:
                drawing_count = 0

            low_text_scan_signal = len(text) < 150
            has_visual_signal = image_count > 0 or image_blocks > 0 or drawing_count >= 5 or low_text_scan_signal
            if not has_visual_signal:
                continue

            score = (
                image_count * 10.0
                + image_blocks * 10.0
                + min(drawing_count, 80) * 0.35
                + (5.0 if low_text_scan_signal else 0.0)
            )
            scored_pages.append((score, idx))

        if not scored_pages:
            # If PyMuPDF cannot detect visual structure, sample across the whole
            # document instead of falling back to the first pages only.
            if max_pages == 1:
                return [0]
            sampled = sorted({
                min(total_pages - 1, round(i * (total_pages - 1) / (max_pages - 1)))
                for i in range(max_pages)
            })
            return sampled[:max_pages]

        selected = sorted(idx for _, idx in sorted(scored_pages, reverse=True)[:max_pages])
        logger.info(
            "Selected PDF pages for vision: %s of %d total pages",
            [idx + 1 for idx in selected],
            total_pages,
        )
        return selected

    async def _vision_model_extract(self, file_path: str, filename: str) -> str:
        """
        Ask a local/cloud vision model to describe grading-relevant visual evidence.
        """
        from app.config import settings
        from app.services.llm_provider import ChatMessage, build_vision_llm_from_env

        llm = build_vision_llm_from_env()
        model = settings.DEDICATED_VISION_MODEL or settings.GRADIENT_VISION_OCR_MODEL
        if not llm or not model:
            raise ValueError(
                "Visual extraction is enabled, but no vision model is configured. "
                "Set DEDICATED_VISION_MODEL or GRADIENT_VISION_OCR_MODEL."
            )

        mime = self._mime_for_path(file_path)
        with open(file_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()

        prompt = (
            "Analyze this student submission image for grading. It may contain a diagram, flowchart, "
            "graph, chart, table, UI design, architecture sketch, ERD, UML diagram, circuit, layout, "
            "screenshot, or handwritten visual answer.\n\n"
            "Do NOT just OCR it. Produce structured grading evidence:\n"
            "1. Visible title/labels/text, if any.\n"
            "2. Main components/nodes/screens/shapes/rows/columns.\n"
            "3. Connections, arrows, hierarchy, sequence, or data flow.\n"
            "4. For graphs/charts: axes, units, legend, trends, outliers, and approximate values.\n"
            "5. For tables: headers, key rows/columns, totals, comparisons, and anomalies.\n"
            "6. Design/layout observations and missing/unclear parts.\n"
            "7. Any assumptions you are making because the image is ambiguous.\n\n"
            "Be concrete and faithful to the image. Do not invent unseen details."
        )

        resp = await llm.chat(
            messages=[
                ChatMessage(
                    role="user",
                    content=[
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime};base64,{b64}"},
                        },
                    ],
                )
            ],
            model=model,
            temperature=0.0,
            max_tokens=2048,
        )
        logger.info("Vision model extracted %d chars of visual evidence from %s", len(resp.text), filename)
        return resp.text.strip()

    def _mime_for_path(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower()
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
        }.get(ext, "image/png")


ocr_service = OCRService()

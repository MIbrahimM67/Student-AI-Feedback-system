"""Small, explicit input limits for the document demonstration deployment."""
import io
from pathlib import Path
import zipfile

from fastapi import HTTPException
from app.config import settings


def check_submission_type(kind: str) -> None:
    if kind == "coding" and (settings.DOCUMENT_DEMO or not settings.CODE_EXECUTION_ENABLED):
        raise HTTPException(503, "Code grading is paused. Submit a document instead.")


def validate_document(content: bytes, filename: str) -> None:
    if not settings.DOCUMENT_DEMO:
        return
    if len(content) > settings.DEMO_MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(413, f"Demo documents must be at most {settings.DEMO_MAX_FILE_MB} MB.")
    extension = Path(filename).suffix.lower()
    if extension not in {".pdf", ".docx", ".txt", ".png", ".jpg", ".jpeg"}:
        raise HTTPException(415, "Demo supports PDF, DOCX, TXT, PNG and JPEG documents only.")
    try:
        if extension == ".pdf":
            import fitz
            with fitz.open(stream=content, filetype="pdf") as doc:
                if doc.needs_pass or not 0 < len(doc) <= settings.DEMO_MAX_PDF_PAGES:
                    raise HTTPException(422, f"Use an unlocked PDF with 1–{settings.DEMO_MAX_PDF_PAGES} pages.")
                # Bound rendered images, including PDFs with unusually large page dimensions.
                if any(page.rect.width * page.rect.height > 2_000_000 for page in doc):
                    raise HTTPException(422, "PDF pages are too large for this demo.")
        elif extension == ".docx":
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = archive.infolist()
                if len(members) > 2000 or sum(m.file_size for m in members) > 20 * 1024 * 1024:
                    raise HTTPException(413, "DOCX expands beyond the demo's 20 MB limit.")
                if "word/document.xml" not in archive.namelist():
                    raise ValueError("Not a DOCX document")
        elif extension in {".png", ".jpg", ".jpeg"}:
            from PIL import Image
            with Image.open(io.BytesIO(content)) as img:
                if img.width * img.height > 12_000_000:
                    raise HTTPException(413, "Demo images must be at most 12 megapixels.")
                img.verify()
        elif len(content.decode("utf-8")) > settings.DEMO_MAX_TEXT_CHARS:
            raise HTTPException(413, "Text is too long for this demo.")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(422, "Document is invalid or unreadable.") from exc


async def read_upload(file) -> bytes:
    # Avoid reading an arbitrarily large body into the small API process.
    if not settings.DOCUMENT_DEMO:
        return await file.read()
    content = await file.read(settings.DEMO_MAX_FILE_MB * 1024 * 1024 + 1)
    validate_document(content, file.filename or "")
    return content

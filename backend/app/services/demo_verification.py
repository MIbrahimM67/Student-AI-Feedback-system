"""Opt-in deployment verification using synthetic documents and real credentials."""
import asyncio
import logging
import tempfile
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


async def verify_demo_providers() -> None:
    from app.auth.firebase import _init_firebase
    from firebase_admin import auth
    from app.grading.pipeline import grade_submission

    _init_firebase()
    uid = next(value.strip() for value in settings.DEMO_ALLOWED_UIDS.split(",") if value.strip())
    await asyncio.to_thread(auth.get_user, uid)
    logger.warning("Document demo verification: firebase_user=ok")

    with tempfile.TemporaryDirectory(prefix="gradewise-verification-") as directory:
        submission = Path(directory) / "answer.txt"
        reference = Path(directory) / "reference.txt"
        submission.write_text("Water freezes at zero degrees Celsius at standard atmospheric pressure.")
        reference.write_text("At standard atmospheric pressure, water freezes at 0 degrees Celsius.")
        result = await grade_submission(
            submission_path=str(submission), reference_path=str(reference),
            raw_rubric="Award up to 10 points for correctly stating water's freezing point at standard pressure.",
            org_id="deployment-verification", subject_id="deployment-verification",
        )
    if result.max_score <= 0 or not result.feedback.strip():
        raise RuntimeError("Document demo verification returned an incomplete grading report")
    logger.warning("Document demo verification: text_grading=ok score=%s max_score=%s", result.score, result.max_score)

    if settings.VISUAL_EXTRACTION_ENABLED:
        import fitz
        from app.services.ocr_service import ocr_service
        with tempfile.TemporaryDirectory(prefix="gradewise-vision-verification-") as directory:
            image = Path(directory) / "freezing-point.png"
            with fitz.open() as document:
                page = document.new_page(width=320, height=160)
                page.insert_text((20, 55), "Water freezes at 0 degrees Celsius.", fontsize=12)
                page.get_pixmap().save(str(image))
            evidence = await ocr_service.extract_text(str(image), image.name)
            if not evidence.strip():
                raise RuntimeError("Document demo verification returned no visual evidence")
        logger.warning("Document demo verification: vision_extraction=ok")

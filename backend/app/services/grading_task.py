"""
GradeWise v3 — grading task helpers.

Called by Celery `grade_submission` task.
Orchestrates: load submission → extract text → scan → pipeline → persist.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone

from app.config import settings
from app.db.postgres import get_conn
from app.db.vectors import upsert_submission_chunks
from app.services.feedback_pipeline import run_pipeline
from app.services.llm_provider import build_llm_from_env
from app.services.ocr_service import ocr_service
from app.services.warning_service import warning_service

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


async def get_batch_submission_ids(batch_id: str, org_id: str) -> list[str]:
    """Return all submission IDs for a batch (used by run_batch_grading task)."""
    async with get_conn(org_id) as conn:
        rows = await conn.fetch(
            "SELECT id FROM submissions WHERE batch_id = $1 AND status = 'uploaded'",
            batch_id,
        )
    return [str(r["id"]) for r in rows]


async def run_grade_submission(submission_id: str, org_id: str) -> None:
    """
    Full grading flow for one submission:
      1. Load submission + assignment + rubric from Postgres
      2. Extract text (file download + OCR if needed)
      3. Policy scan
      4. Code sandbox (if coding)
      5. Run 10-step pipeline
      6. Persist feedback_report

    NOTE: The Celery worker is a separate process from FastAPI, so the asyncpg
    pool is never initialized by the app lifespan. We lazily initialize it here.
    """
    from app.db.postgres import init_pool, _pool
    pool_was_none = _pool is None
    if pool_was_none:
        logger.info("Database pool not initialized — initializing now for Celery worker.")
        await init_pool()

    llm = build_llm_from_env()
    redis = aioredis.from_url(os.environ["REDIS_URL"], decode_responses=True)

    # ---- Load submission -----------------------------------------------------
    async with get_conn(org_id) as conn:
        sub = await conn.fetchrow(
            "SELECT * FROM submissions WHERE id = $1", submission_id
        )
        if not sub:
            logger.error("Submission %s not found", submission_id)
            return

        await conn.execute(
            "UPDATE submissions SET status = 'processing' WHERE id = $1", submission_id
        )

        # Load assignment + rubric
        assignment = None
        questions = []
        rubric_criteria = []
        if sub["assignment_id"]:
            assignment = await conn.fetchrow(
                "SELECT * FROM assignments WHERE id = $1", sub["assignment_id"]
            )
            questions = [dict(r) for r in await conn.fetch(
                "SELECT * FROM questions WHERE assignment_id = $1 ORDER BY display_order",
                sub["assignment_id"],
            )]
            rubric_criteria = [dict(r) for r in await conn.fetch(
                "SELECT * FROM rubric_criteria WHERE assignment_id = $1",
                sub["assignment_id"],
            )]

        # Load student profile
        student = await conn.fetchrow(
            "SELECT display_name FROM users WHERE uid = $1", sub["user_id"]
        ) if sub["user_id"] else None

    student_name = student["display_name"] if student else (sub["student_name"] or "Student")
    subject_id = str(sub["subject_id"]) if sub["subject_id"] else None
    batch_id = str(sub["batch_id"]) if sub["batch_id"] else None

    # ---- Extract text -------------------------------------------------------
    extracted_text = sub["input_text"] or ""

    if sub["file_url"] and not extracted_text.strip():
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(sub["file_url"])
                resp.raise_for_status()

            ext = os.path.splitext(sub["file_name"] or ".pdf")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name

            extracted_text = await ocr_service.extract_text(tmp_path, sub["file_name"] or "file")
            os.remove(tmp_path)
        except Exception as e:
            logger.error("Text extraction failed for submission %s: %s", submission_id, e)
            await _mark_failed(org_id, submission_id, batch_id)
            return

    if not extracted_text.strip():
        await _mark_failed(org_id, submission_id, batch_id)
        return

    # ---- Extract reference text ---------------------------------------------
    reference_text = None
    if sub.get("reference_file_url"):
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(sub["reference_file_url"])
                resp.raise_for_status()

            ext = os.path.splitext(sub.get("reference_file_name") or ".pdf")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name

            reference_text = await ocr_service.extract_text(tmp_path, sub.get("reference_file_name") or "reference_file")
            os.remove(tmp_path)
        except Exception as e:
            logger.warning("Reference text extraction failed for submission %s: %s", submission_id, e)

    # ---- Policy scan --------------------------------------------------------
    is_violated, reason = await warning_service.scan_and_enforce(
        org_id=org_id,
        user_id=str(sub["user_id"]) if sub["user_id"] else "batch",
        submission_id=submission_id,
        text=extracted_text,
    )
    if is_violated:
        async with get_conn(org_id) as conn:
            await conn.execute(
                "UPDATE submissions SET status = 'failed' WHERE id = $1", submission_id
            )
        return

    # ---- Code sandbox -------------------------------------------------------
    code_execution_result = None
    if sub["type"] == "coding":
        try:
            from app.services.code_sandbox_service import code_sandbox_service
            ext = os.path.splitext(sub["file_name"] or ".py")[1].lower()
            lang = "python" if ext == ".py" else ("cpp" if ext in (".cpp", ".cc") else "java")
            result = await code_sandbox_service.execute_code(extracted_text, lang)
            code_execution_result = (
                f"Exit code: {result.get('exitCode')}\n"
                f"Stdout:\n{result.get('stdout', '')}\n"
                f"Stderr:\n{result.get('stderr', '')}"
            )
        except Exception as e:
            logger.warning("Code sandbox failed: %s", e)

    # ---- Build pipeline inputs ----------------------------------------------
    # If no assignment/questions, create a generic single-question wrapper
    if not questions:
        q_text = sub.get("question_text") or "Evaluate the overall quality of this submission."
        r_text = sub.get("rubric_text") or "Evaluate comprehensively."
        questions = [{
            "id": str(uuid.uuid4()),
            "text": q_text,
            "max_marks": 100,
            "display_order": 0,
        }]
        rubric_criteria = [{
            "id": str(uuid.uuid4()),
            "name": "Overall Quality",
            "max_score": 100,
            "description": r_text,
        }]

    assignment_version = assignment["version"] if assignment else 1

    # ---- Run pipeline -------------------------------------------------------
    try:
        report = await run_pipeline(
            llm=llm,
            redis=redis,
            org_id=org_id,
            subject_id=subject_id or str(uuid.uuid4()),
            assignment_id=str(sub["assignment_id"]) if sub["assignment_id"] else str(uuid.uuid4()),
            assignment_version=assignment_version,
            questions=questions,
            rubric_criteria=rubric_criteria,
            student_answer=extracted_text,
            student_name=student_name,
            submission_id=submission_id,
            code_execution_result=code_execution_result,
            reference_text=reference_text,
        )
    except Exception as e:
        logger.error("Pipeline failed for submission %s: %s", submission_id, e)
        await _mark_failed(org_id, submission_id, batch_id)
        return
    finally:
        await redis.aclose()

    # ---- Persist feedback_report --------------------------------------------
    now = datetime.now(timezone.utc)
    report_dict = report.model_dump()
    avg_confidence = (
        sum(s.confidence for s in report.rubricScores) / len(report.rubricScores)
        if report.rubricScores else 0.5
    )
    needs_review = report.status == "needs_review"

    report_id = str(uuid.uuid4())
    async with get_conn(org_id) as conn:
        await conn.execute(
            """
            INSERT INTO feedback_reports
              (id, org_id, submission_id, batch_id,
               ai_overall_score, ai_max_score, ai_status,
               ai_payload, ai_overall_confidence, ai_generated_at,
               ai_model_versions)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
            """,
            report_id, org_id, submission_id, batch_id,
            report.overallScore, report.maxScore, report.status,
            json.dumps(report_dict),
            avg_confidence, now,
            json.dumps({
                "specialist": settings.GRADIENT_MODEL_SPECIALIST,
                "judge": settings.GRADIENT_MODEL_JUDGE,
                "senior": settings.GRADIENT_MODEL_SENIOR,
            }),
        )
        await conn.execute(
            "UPDATE submissions SET status = 'graded' WHERE id = $1", submission_id
        )
        if batch_id:
            col = "needs_review_count" if needs_review else "processed_files"
            await conn.execute(
                f"UPDATE batches SET {col} = {col} + 1 WHERE id = $1", batch_id
            )


async def _mark_failed(org_id: str, submission_id: str, batch_id: str | None) -> None:
    async with get_conn(org_id) as conn:
        await conn.execute(
            "UPDATE submissions SET status = 'failed' WHERE id = $1", submission_id
        )
        if batch_id:
            await conn.execute(
                "UPDATE batches SET processed_files = processed_files + 1 WHERE id = $1",
                batch_id,
            )

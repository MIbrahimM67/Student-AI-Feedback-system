"""
GradeWise v3 — student routes.

POST /api/student/submissions          — submit for grading (enqueues Celery task)
GET  /api/student/submissions          — list my submissions
GET  /api/student/submissions/{id}     — get one submission
GET  /api/student/submissions/{id}/feedback — get feedback report (published only)
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status

from app.auth.firebase import verify_id_token, get_storage_bucket
from app.db.postgres import get_conn
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- Auth dependency --------------------------------------------------------

async def _get_verified_uid(authorization: Annotated[str, Header()]) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        claims = verify_id_token(token)
        return claims["uid"]
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}") from e


async def _get_student_profile(uid: str = Depends(_get_verified_uid)) -> dict:
    """Verify user is a student and not blocked."""
    async with get_conn() as conn:
        org_id = await conn.fetchval("SELECT get_user_org_id($1)", uid)

    if not org_id:
        raise HTTPException(404, "User not found. Sign in again.")

    async with get_conn(str(org_id)) as conn:
        row = await conn.fetchrow(
            "SELECT uid, org_id, role, blocked_until FROM users WHERE uid = $1", uid
        )

    if not row:
        raise HTTPException(404, "User not found. Sign in again.")
    if row["role"] not in ("student", "instructor", "admin"):
        raise HTTPException(403, "Account role not set. Complete onboarding first.")
    if row["blocked_until"] and row["blocked_until"] > datetime.now(timezone.utc):
        raise HTTPException(403, f"Account suspended until {row['blocked_until'].isoformat()}.")
    return dict(row)


# ---- POST /submissions -------------------------------------------------------

@router.post("/submissions", status_code=202)
async def create_submission(
    assignment_id: Optional[str] = Form(None),
    subject_id: Optional[str] = Form(None),
    type: str = Form(...),          # text | handwritten | coding | custom
    question_text: Optional[str] = Form(""),
    rubric_text: Optional[str] = Form(""),
    input_text: Optional[str] = Form(""),
    reference_file: Optional[UploadFile] = File(None),
    file: Optional[UploadFile] = File(None),
    user: dict = Depends(_get_student_profile),
):
    """
    Accept a student submission and enqueue it for grading.
    Returns immediately with submission_id — grading runs in background.
    Poll GET /submissions/{id} for status.
    """
    from app.config import settings

    uid = user["uid"]
    org_id = user["org_id"]
    submission_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    file_url = None
    file_name = None

    # ---- File upload (Firebase Storage) -------------------------------------
    if file and file.filename:
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)

        if file_size_mb > settings.STUDENT_MAX_FILE_MB:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the {settings.STUDENT_MAX_FILE_MB}MB student limit.",
            )

        file_name = file.filename
        blob_name = f"submissions/{uid}/{submission_id}_{file_name}"

        try:
            bucket = get_storage_bucket()
            with tempfile.NamedTemporaryFile(
                delete=False, suffix=os.path.splitext(file_name)[1]
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            blob = bucket.blob(blob_name)
            blob.upload_from_filename(tmp_path)
            blob.make_public()
            file_url = blob.public_url
        except Exception as e:
            logger.error("Storage upload failed: %s", e)
            raise HTTPException(500, "File upload failed. Please try again.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    # ---- Reference File upload (Firebase Storage) ---------------------------
    reference_file_url = None
    reference_file_name = None
    if reference_file and reference_file.filename:
        content = await reference_file.read()
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > settings.STUDENT_MAX_FILE_MB:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Reference file exceeds the {settings.STUDENT_MAX_FILE_MB}MB student limit.",
            )
        reference_file_name = reference_file.filename
        blob_name = f"submissions/{uid}/{submission_id}_ref_{reference_file_name}"
        try:
            bucket = get_storage_bucket()
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(reference_file_name)[1]) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            blob = bucket.blob(blob_name)
            blob.upload_from_filename(tmp_path)
            blob.make_public()
            reference_file_url = blob.public_url
        except Exception as e:
            logger.error("Reference storage upload failed: %s", e)
            raise HTTPException(500, "Reference file upload failed.")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    if not input_text and not file_url:
        raise HTTPException(400, "Provide either input_text or a file.")

    # ---- Write submission row to Postgres -----------------------------------
    async with get_conn(org_id) as conn:
        await conn.execute(
            """
            INSERT INTO submissions
              (id, org_id, user_id, assignment_id, subject_id,
               type, mode, question_text, rubric_text, input_text, 
               reference_file_url, reference_file_name, file_url, file_name, status, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,'single',$7,$8,$9,$10,$11,$12,$13,'uploaded',$14)
            """,
            submission_id, org_id, uid,
            assignment_id, subject_id,
            type, question_text or None, rubric_text or None, input_text or None,
            reference_file_url, reference_file_name, file_url, file_name, now,
        )

    # ---- Enqueue grading task -----------------------------------------------
    celery_app.send_task(
        "tasks.grade_submission",
        args=[submission_id, org_id],
    )

    return {
        "submission_id": submission_id,
        "status": "uploaded",
        "message": "Submission received. Grading has started — check back in ~30 seconds.",
    }


# ---- GET /submissions -------------------------------------------------------

@router.get("/submissions")
async def list_submissions(user: dict = Depends(_get_student_profile)):
    """List the current student's submissions, newest first."""
    uid = user["uid"]
    org_id = user["org_id"]

    async with get_conn(org_id) as conn:
        rows = await conn.fetch(
            """
            SELECT s.id, s.type, s.mode, s.file_name, s.status, s.created_at,
                   fr.ai_overall_score, fr.ai_max_score, fr.final_status,
                   fr.published_at
            FROM submissions s
            LEFT JOIN feedback_reports fr ON fr.submission_id = s.id
            WHERE s.user_id = $1
            ORDER BY s.created_at DESC
            LIMIT 50
            """,
            uid,
        )

    return {"submissions": [dict(r) for r in rows]}


# ---- GET /submissions/{id} --------------------------------------------------

@router.get("/submissions/{submission_id}")
async def get_submission(
    submission_id: str,
    user: dict = Depends(_get_student_profile),
):
    uid = user["uid"]
    org_id = user["org_id"]

    async with get_conn(org_id) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM submissions WHERE id = $1 AND user_id = $2",
            submission_id, uid,
        )

    if not row:
        raise HTTPException(404, "Submission not found.")

    return dict(row)


# ---- GET /submissions/{id}/feedback -----------------------------------------

@router.get("/submissions/{submission_id}/feedback")
async def get_feedback(
    submission_id: str,
    user: dict = Depends(_get_student_profile),
):
    """
    Returns the feedback report for a submission.
    Students can only see the report once it is published (instructor approved).
    """
    uid = user["uid"]
    org_id = user["org_id"]

    async with get_conn(org_id) as conn:
        # Verify the submission belongs to this student
        sub = await conn.fetchrow(
            "SELECT id, status FROM submissions WHERE id = $1 AND user_id = $2",
            submission_id, uid,
        )
        if not sub:
            raise HTTPException(404, "Submission not found.")

        report = await conn.fetchrow(
            """
            SELECT id, ai_overall_score, ai_max_score, final_status,
                   final_payload, pdf_url, published_at, created_at
            FROM feedback_reports
            WHERE submission_id = $1 AND published_at IS NOT NULL
            """,
            submission_id,
        )

    if not report:
        # Return processing status if grading is still in progress
        return {
            "status": sub["status"],
            "message": (
                "Your feedback is being graded. Check back in ~30 seconds."
                if sub["status"] in ("uploaded", "processing")
                else "Feedback is awaiting instructor approval."
            ),
        }

    # Parse the AI payload from the DB (stored as JSONB string or dict)
    import json as _json
    payload = report["final_payload"]
    if isinstance(payload, str):
        payload = _json.loads(payload)
    if payload is None:
        payload = {}

    return {
        "report": {
            "id": str(report["id"]),
            "submissionId": submission_id,
            "overallScore": float(report["ai_overall_score"] or 0),
            "maxScore": float(report["ai_max_score"] or 100),
            "status": report["final_status"] or payload.get("status", "needs_review"),
            "summary": payload.get("summary", ""),
            "strengths": payload.get("strengths", []),
            "weaknesses": payload.get("weaknesses", []),
            "suggestions": payload.get("suggestions", []),
            "finalComments": payload.get("finalComments", ""),
            "rubricScores": payload.get("rubricScores", []),
            "extractedText": payload.get("extractedText", ""),
            "pdfUrl": report["pdf_url"],
            "publishedAt": report["published_at"].isoformat() if report["published_at"] else None,
        }
    }

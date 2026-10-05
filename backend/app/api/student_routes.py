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

from app.auth.firebase import verify_id_token
from app.services import file_storage
from app.services.demo_limits import check_submission_type, read_upload
from app.db.postgres import get_conn
from app.services.task_dispatch import dispatch, notify

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
    stdin_text: Optional[str] = Form(""),
    code_language: str = Form("python"),
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

    check_submission_type(type)
    if type == "coding" and code_language not in {"python", "cpp", "java"}:
        raise HTTPException(422, "Choose Python, C++ or Java.")
    if settings.DOCUMENT_DEMO and len(input_text or "") > settings.DEMO_MAX_TEXT_CHARS:
        raise HTTPException(413, "Text is too long for this demo.")
    uid = user["uid"]
    org_id = user["org_id"]
    submission_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    file_url = None
    file_name = ({"python": "solution.py", "cpp": "solution.cpp", "java": "Main.java"}[code_language]
                 if type == "coding" else None)

    # ---- File upload (Firebase Storage) -------------------------------------
    if file and file.filename:
        content = await read_upload(file, kind=type)
        file_size_mb = len(content) / (1024 * 1024)

        if file_size_mb > settings.STUDENT_MAX_FILE_MB:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds the {settings.STUDENT_MAX_FILE_MB}MB student limit.",
            )

        file_name = file.filename
        if type == "coding" and file_name.lower().endswith(".txt"):
            file_name = {"python": "solution.py", "cpp": "solution.cpp", "java": "Main.java"}[code_language]
        blob_name = f"submissions/{uid}/{submission_id}_{file_name}"

        try:
            file_url = await file_storage.save_file(content, blob_name, org_id=org_id, owner_uid=uid)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Storage upload failed: %s", e)
            raise HTTPException(500, "File upload failed. Please try again.")

    # ---- Reference File upload (Firebase Storage) ---------------------------
    reference_file_url = None
    reference_file_name = None
    if reference_file and reference_file.filename:
        content = await read_upload(reference_file)
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > settings.STUDENT_MAX_FILE_MB:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Reference file exceeds the {settings.STUDENT_MAX_FILE_MB}MB student limit.",
            )
        reference_file_name = reference_file.filename
        blob_name = f"submissions/{uid}/{submission_id}_ref_{reference_file_name}"
        try:
            reference_file_url = await file_storage.save_file(content, blob_name, org_id=org_id, owner_uid=uid)
        except HTTPException:
            raise
        except Exception as e:
            logger.error("Reference storage upload failed: %s", e)
            raise HTTPException(500, "Reference file upload failed.")

    if not input_text and not file_url:
        raise HTTPException(400, "Provide either input_text or a file.")

    # ---- Write submission row to Postgres -----------------------------------
    async with get_conn(org_id) as conn:
        await conn.execute(
            """
            INSERT INTO submissions
              (id, org_id, user_id, assignment_id, subject_id,
               type, mode, question_text, rubric_text, input_text, stdin_text,
               reference_file_url, reference_file_name, file_url, file_name, status, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,'single',$7,$8,$9,$10,$11,$12,$13,$14,'uploaded',$15)
            """,
            submission_id, org_id, uid,
            assignment_id, subject_id,
            type, question_text or None, rubric_text or None, input_text or None, stdin_text or None,
            reference_file_url, reference_file_name, file_url, file_name, now,
        )

        # Persist the job in the same transaction as its submission on the demo.
        await dispatch("tasks.grade_submission", [submission_id, org_id], conn=conn)
    notify()
    if not settings.DOCUMENT_DEMO:
        await dispatch("tasks.grade_submission", [submission_id, org_id])

    return {
        "submission_id": submission_id,
        "status": "uploaded",
        "message": "Submission queued. Keep this page open while grading; it may take several minutes.",
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
            SELECT s.id, s.type, s.mode, s.file_name, s.question_text, s.status, s.created_at,
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


# ---- DELETE /submissions/{id} -----------------------------------------------

@router.delete("/submissions/{submission_id}")
async def delete_submission(
    submission_id: str,
    user: dict = Depends(_get_student_profile),
):
    uid = user["uid"]
    org_id = user["org_id"]

    async with get_conn(org_id) as conn:
        # Check ownership first
        row = await conn.fetchrow(
            "SELECT id FROM submissions WHERE id = $1 AND user_id = $2",
            submission_id, uid,
        )
        if not row:
            raise HTTPException(404, "Submission not found or unauthorized.")

        # Delete it (assuming ON DELETE CASCADE for feedback_reports etc.)
        await conn.execute("DELETE FROM submissions WHERE id = $1", submission_id)

    return {"message": "Submission deleted successfully."}


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


@router.get("/submissions/{submission_id}/pdf")
async def download_student_pdf(
    submission_id: str,
    user: dict = Depends(_get_student_profile),
):
    """
    Downloads the student's graded feedback report as a well-formatted PDF.
    """
    from app.services.report_service import report_service
    from fastapi.responses import Response
    import json as _json

    uid = user["uid"]
    org_id = user["org_id"]

    async with get_conn(org_id) as conn:
        sub = await conn.fetchrow(
            """
            SELECT s.*, a.title as assignment_title,
                   COALESCE(fr.final_overall_score, fr.ai_overall_score) as score,
                   COALESCE(fr.final_max_score, fr.ai_max_score) as max_score,
                   COALESCE(fr.final_status, fr.ai_status) as status,
                   COALESCE(fr.final_payload, fr.ai_payload) as payload,
                   pr.similarity_score as plagiarism_similarity_score
            FROM submissions s
            LEFT JOIN feedback_reports fr ON fr.submission_id = s.id
            LEFT JOIN assignments a ON a.id = s.assignment_id
            LEFT JOIN plagiarism_reports pr ON pr.submission_id = s.id
            WHERE s.id = $1 AND s.user_id = $2
            """,
            submission_id, uid,
        )
        if not sub:
            raise HTTPException(404, "Submission not found.")
        if not sub["payload"]:
            raise HTTPException(404, "Feedback report has not been published yet.")

    raw_payload = sub["payload"]
    payload = {}
    if isinstance(raw_payload, str):
        try:
            payload = _json.loads(raw_payload)
        except Exception:
            pass
    elif raw_payload:
        payload = dict(raw_payload)

    payload["score"] = sub["score"] or 0
    payload["max_score"] = sub["max_score"] or 100
    payload["status"] = sub["status"] or "completed"
    if sub["plagiarism_similarity_score"] is not None:
        payload["plagiarism_similarity_score"] = float(sub["plagiarism_similarity_score"])

    student_name = sub["student_name"] or user.get("display_name") or "Student"
    pdf_bytes = report_service.generate_student_pdf_bytes(
        report_data=payload,
        student_name=student_name,
        assignment_type=sub["type"] or "text",
        file_name=sub["file_name"] or "assignment",
        assignment_title=sub["assignment_title"] or "Assignment Submission",
    )

    safe_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_Feedback_Report.pdf"'}
    )


# ---- Faculty upgrade application ------------------------------------------------

from pydantic import BaseModel

class FacultyApplicationBody(BaseModel):
    full_name: str
    university: str
    department: str
    designation: str
    official_email: str

@router.post("/apply-for-instructor")
async def apply_for_instructor(
    body: FacultyApplicationBody,
    user: dict = Depends(_get_student_profile),
):
    """
    Lets a student submit a faculty upgrade application.
    Creates a faculty_applications row and sets the user's faculty_status = 'pending'.
    """
    uid = user["uid"]
    org_id = str(user["org_id"])
    now = datetime.now(timezone.utc)

    async with get_conn(org_id) as conn:
        # Prevent duplicate applications
        existing = await conn.fetchrow(
            "SELECT status FROM faculty_applications WHERE user_id = $1 AND status = 'pending'",
            uid
        )
        if existing:
            raise HTTPException(400, "You already have a pending application. Please wait for review.")

        await conn.execute(
            """
            INSERT INTO faculty_applications
              (org_id, user_id, full_name, university, department, designation, official_email, status)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, 'pending')
            """,
            org_id, uid,
            body.full_name, body.university, body.department,
            body.designation, body.official_email,
        )
        await conn.execute(
            "UPDATE users SET faculty_status = 'pending', updated_at = $1 WHERE uid = $2",
            now, uid,
        )

    return {"status": "submitted", "message": "Application submitted and under admin review."}


@router.get("/my-application")
async def get_my_application(user: dict = Depends(_get_student_profile)):
    """
    Returns the most recent faculty application for the authenticated user.
    """
    uid = user["uid"]
    org_id = str(user["org_id"])

    async with get_conn(org_id) as conn:
        row = await conn.fetchrow(
            """
            SELECT id, full_name, university, department, designation,
                   official_email, status, rejection_reason, created_at
            FROM faculty_applications
            WHERE user_id = $1
            ORDER BY created_at DESC
            LIMIT 1
            """,
            uid,
        )

    if not row:
        return {"application": None}

    return {"application": dict(row)}



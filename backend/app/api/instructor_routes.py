"""
GradeWise v3 — instructor routes (Postgres-backed).

POST /api/instructor/subjects                    — create subject workspace
GET  /api/instructor/subjects                    — list my subjects
POST /api/instructor/subjects/{id}/references    — upload reference material → queues indexing
POST /api/instructor/batch                       — upload batch → queues grading
GET  /api/instructor/batch/{id}                  — batch status
GET  /api/instructor/batch/{id}/reports          — list reports in batch
POST /api/instructor/batch/{id}/reports/{rid}/approve — instructor approve grade
"""
from __future__ import annotations

import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Annotated, List, Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, Form,
    Header, HTTPException, UploadFile, status,
)
from pydantic import BaseModel

from app.auth.firebase import verify_id_token
from app.services import local_storage
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
        return verify_id_token(token)["uid"]
    except Exception as e:
        raise HTTPException(401, str(e)) from e


async def _get_instructor(uid: str = Depends(_get_verified_uid)) -> dict:
    # First, get the org_id bypassing RLS (SECURITY DEFINER function)
    async with get_conn() as conn:
        org_id = await conn.fetchval("SELECT get_user_org_id($1)", uid)
    if not org_id:
        raise HTTPException(404, "User not found.")
    # Now query with RLS context
    async with get_conn(str(org_id)) as conn:
        row = await conn.fetchrow(
            "SELECT uid, org_id, role, faculty_status FROM users WHERE uid = $1", uid
        )
    if not row:
        raise HTTPException(404, "User not found.")
    if row["role"] not in ("instructor", "admin"):
        raise HTTPException(403, "Instructor role required.")
    return dict(row)


# ---- Subjects ---------------------------------------------------------------

class CreateSubjectRequest(BaseModel):
    title: str
    code: Optional[str] = None
    description: Optional[str] = None
    level: Optional[str] = None
    language: str = "en"

@router.post("/subjects", status_code=201)
async def create_subject(
    body: CreateSubjectRequest,
    user: dict = Depends(_get_instructor),
):
    title = body.title
    code = body.code
    description = body.description
    level = body.level
    language = body.language
    now = datetime.now(timezone.utc)

    try:
        async with get_conn(user["org_id"]) as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO subjects
                  (org_id, instructor_id, code, title, description,
                   level, language, kb_status, created_at, updated_at)
                VALUES ($1::uuid,$2,$3,$4,$5,$6,$7,'empty',$8,$8)
                RETURNING *
                """,
                user["org_id"], user["uid"],
                code, title, description, level, language, now,
            )
        return {"subject": dict(row)}
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"Failed to create subject: {error_details}")
        raise HTTPException(400, f"Error: {str(e)} | Details: {error_details}")


@router.get("/subjects")
async def list_subjects(user: dict = Depends(_get_instructor)):
    async with get_conn(user["org_id"]) as conn:
        rows = await conn.fetch(
            """
            SELECT id, code, title, description, level, language,
                   kb_status, reference_count, assignment_count, expires_at, created_at
            FROM subjects
            WHERE instructor_id = $1
            ORDER BY created_at DESC
            """,
            user["uid"],
        )
    return {"subjects": [dict(r) for r in rows]}

@router.post("/subjects/{subject_id}/renew")
async def renew_subject(subject_id: str, user: dict = Depends(_get_instructor)):
    async with get_conn(user["org_id"]) as conn:
        row = await conn.fetchrow(
            """
            UPDATE subjects
            SET expires_at = now() + interval '1 month'
            WHERE id = $1 AND instructor_id = $2
            RETURNING expires_at
            """,
            subject_id, user["uid"]
        )
        if not row:
            raise HTTPException(404, "Subject not found or you do not have access.")
    return {"message": "Subject renewed successfully", "expires_at": row["expires_at"]}


# ---- Reference material upload → indexing -----------------------------------

@router.post("/subjects/{subject_id}/references", status_code=202)
async def upload_reference(
    subject_id: str,
    title: str = Form(...),
    ref_type: str = Form("textbook"),
    file: UploadFile = File(...),
    user: dict = Depends(_get_instructor),
):
    """
    Upload a reference material (PDF/DOCX/TXT) and queue chunking + embedding.
    """
    from app.config import settings

    org_id = user["org_id"]
    ref_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > 50:
        raise HTTPException(413, "Reference file must be under 50MB.")

    # Upload to Local Storage
    blob_name = f"references/{org_id}/{subject_id}/{ref_id}_{file.filename}"
    try:
        file_url = local_storage.save_file(content, blob_name)
    except Exception as e:
        logger.error("Local storage upload failed: %s", e, exc_info=True)
        raise HTTPException(500, f"File upload failed: {e}")


    async with get_conn(org_id) as conn:
        await conn.execute(
            """
            INSERT INTO reference_materials
              (id, org_id, subject_id, title, type, file_url, index_status, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,'pending',$7)
            """,
            ref_id, org_id, subject_id, title, ref_type, file_url, now,
        )
        # Update subject reference count
        await conn.execute(
            "UPDATE subjects SET reference_count = reference_count + 1, updated_at = $1 WHERE id = $2",
            now, subject_id,
        )

    # Queue indexing task
    celery_app.send_task(
        "tasks.index_reference_material",
        args=[ref_id, org_id, subject_id],
    )

    return {
        "reference_id": ref_id,
        "status": "pending",
        "message": "File uploaded. Indexing started — knowledge base will be ready in ~1 minute.",
    }

@router.get("/subjects/{subject_id}/references")
async def list_references(
    subject_id: str,
    user: dict = Depends(_get_instructor),
):
    """
    Returns all reference materials uploaded for a specific subject.
    """
    org_id = user["org_id"]
    
    async with get_conn(org_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, title, type, index_status, chunk_count, created_at
            FROM reference_materials
            WHERE subject_id = $1::uuid
            ORDER BY created_at DESC
            """,
            subject_id
        )
        
    return {
        "references": [dict(r) for r in rows]
    }

# ---- Assignments -------------------------------------------------------------

class CreateAssignmentRequest(BaseModel):
    title: str
    prompt: Optional[str] = ""
    rubric: Optional[str] = ""
    plagiarism_enabled: Optional[bool] = False

@router.post("/subjects/{subject_id}/assignments", status_code=201)
async def create_assignment(
    subject_id: str,
    body: CreateAssignmentRequest,
    user: dict = Depends(_get_instructor),
):
    """
    Creates a new assignment under a subject, taking title, prompt, and rubric.
    """
    org_id = user["org_id"]
    title = body.title
    prompt = body.prompt
    rubric = body.rubric
    plagiarism = body.plagiarism_enabled
    
    now = datetime.now(timezone.utc)

    async with get_conn(org_id) as conn:
        # Create assignment
        assignment_row = await conn.fetchrow(
            """
            INSERT INTO assignments (org_id, subject_id, title, plagiarism_enabled, created_at)
            VALUES ($1, $2::uuid, $3, $4, $5)
            RETURNING id
            """,
            org_id, subject_id, title, plagiarism, now,
        )
        assignment_id = assignment_row["id"]
        
        # Save prompt as a single question
        if prompt:
            await conn.execute(
                """
                INSERT INTO questions (org_id, assignment_id, text, max_marks, display_order)
                VALUES ($1, $2, $3, 100, 0)
                """,
                org_id, assignment_id, prompt
            )
            
        # Save rubric as a single criterion
        if rubric:
            await conn.execute(
                """
                INSERT INTO rubric_criteria (org_id, assignment_id, name, max_score, description)
                VALUES ($1, $2, 'General Rubric', 100, $3)
                """,
                org_id, assignment_id, rubric
            )
            
        # Update assignment count
        await conn.execute(
            "UPDATE subjects SET assignment_count = assignment_count + 1, updated_at = $1 WHERE id = $2::uuid",
            now, subject_id,
        )

    return {"id": str(assignment_id), "message": "Assignment created successfully."}


@router.get("/subjects/{subject_id}/assignments")
async def get_assignments(
    subject_id: str,
    user: dict = Depends(_get_instructor),
):
    """
    List assignments for a given subject.
    """
    org_id = user["org_id"]
    async with get_conn(org_id) as conn:
        rows = await conn.fetch(
            "SELECT * FROM assignments WHERE subject_id = $1 ORDER BY created_at DESC",
            subject_id
        )
        
        # We also need to fetch the prompt (question text) and rubric for each
        assignments = []
        for r in rows:
            assn = dict(r)
            
            q_row = await conn.fetchrow(
                "SELECT text FROM questions WHERE assignment_id = $1 ORDER BY display_order LIMIT 1",
                assn["id"]
            )
            assn["prompt"] = q_row["text"] if q_row else ""
            
            r_row = await conn.fetchrow(
                "SELECT description FROM rubric_criteria WHERE assignment_id = $1 LIMIT 1",
                assn["id"]
            )
            assn["rubric"] = r_row["description"] if r_row else ""
            
            assignments.append(assn)
            
    return {"assignments": assignments}

@router.get("/assignments/{assignment_id}/batches")
async def get_assignment_batches(
    assignment_id: str,
    user: dict = Depends(_get_instructor),
):
    """
    List all batches for a given assignment, ordered by creation date.
    """
    org_id = user["org_id"]
    async with get_conn(org_id) as conn:
        rows = await conn.fetch(
            "SELECT * FROM batches WHERE assignment_id = $1::uuid AND instructor_id = $2 ORDER BY created_at DESC",
            assignment_id, user["uid"]
        )
    return {"batches": [dict(r) for r in rows]}

# ---- Single upload ----------------------------------------------------------

@router.post("/single-upload", status_code=202)
async def single_upload(
    assignment_id: str = Form(...),
    subject_id: str = Form(...),
    student_name: str = Form(...),
    plagiarism_enabled: bool = Form(False),
    type: str = Form("text"),
    stdin_text: Optional[str] = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(_get_instructor),
):
    """
    Directly uploads and queues a single student submission for grading.
    """
    org_id = user["org_id"]
    uid = user["uid"]
    
    sub_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    content = await file.read()
    if len(content) > settings.STUDENT_FILE_MAX_MB * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.STUDENT_FILE_MAX_MB}MB limit.")
        
    blob_name = f"submissions/{org_id}/{assignment_id}/{sub_id}_{file.filename}"
    try:
        file_url = local_storage.save_file(content, blob_name)
    except Exception as e:
        logger.error("Local storage upload failed: %s", e)
        raise HTTPException(500, f"File upload failed: {e}")
            
    async with get_conn(org_id) as conn:
        await conn.execute(
            """
            INSERT INTO submissions 
              (id, org_id, assignment_id, type, stdin_text, file_url, status, student_name, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, 'uploaded', $7, $8)
            """,
            sub_id, org_id, assignment_id, type, stdin_text, file_url, student_name, now,
        )
        
    # Queue single processing directly
    from app.workers.celery_app import celery_app
    celery_app.send_task("tasks.grade_submission", args=[sub_id, org_id])
    
    return {
        "submission_id": sub_id,
        "status": "pending",
        "message": f"Submission for {student_name} uploaded. Grading started."
    }

# ---- Batch upload -----------------------------------------------------------

@router.post("/batch", status_code=202)
async def upload_batch(
    assignment_id: str = Form(...),
    subject_id: str = Form(...),
    batch_name: Optional[str] = Form(None),
    plagiarism_enabled: bool = Form(False),
    type: str = Form("text"),
    stdin_text: Optional[str] = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(_get_instructor),
):
    from app.config import settings

    org_id = user["org_id"]
    uid = user["uid"]

    import traceback

    try:
        if not file.filename.lower().endswith(".zip"):
            raise HTTPException(400, "Batch upload must be a single .zip file.")

        batch_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        # Create batch row
        async with get_conn(org_id) as conn:
            await conn.execute(
                """
                INSERT INTO batches
                  (id, org_id, instructor_id, subject_id, assignment_id,
                   batch_name, plagiarism_enabled, status, total_files, processed_files, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,'uploaded',0,0,$8)
                """,
                batch_id, org_id, uid, subject_id, assignment_id,
                batch_name or f"Batch {now.strftime('%b %d, %H:%M')}",
                plagiarism_enabled, now,
            )

        total_size = 0
        submission_ids = []

        content = await file.read()
        if len(content) > settings.INSTRUCTOR_BATCH_MAX_MB * 1024 * 1024:
            raise HTTPException(413, f"Batch exceeds {settings.INSTRUCTOR_BATCH_MAX_MB}MB limit.")

        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
            tmp.write(content)
            tmp_zip_path = tmp.name

        try:
            import zipfile
            import shutil
            with tempfile.TemporaryDirectory() as extract_dir:
                with zipfile.ZipFile(tmp_zip_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_dir)

                # Detect root dir if the zip wraps everything in one master folder
                root_contents = os.listdir(extract_dir)
                if len(root_contents) == 1 and os.path.isdir(os.path.join(extract_dir, root_contents[0])):
                    base_dir = os.path.join(extract_dir, root_contents[0])
                else:
                    base_dir = extract_dir

                student_folders = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
                
                # If no folders found, maybe they zipped files directly instead of folders
                if not student_folders:
                    raise HTTPException(400, "No student folders found inside the ZIP.")

                if len(student_folders) > settings.INSTRUCTOR_BATCH_MAX_FILES:
                     raise HTTPException(400, f"Maximum {settings.INSTRUCTOR_BATCH_MAX_FILES} student folders per batch.")

                # Update batch row with actual student count
                async with get_conn(org_id) as conn:
                    await conn.execute("UPDATE batches SET total_files = $1 WHERE id = $2", len(student_folders), batch_id)

                for student_name in student_folders:
                    student_path = os.path.join(base_dir, student_name)
                    student_zip_base = os.path.join(extract_dir, f"st_{student_name}")
                    shutil.make_archive(student_zip_base, 'zip', student_path)
                    student_zip_path = f"{student_zip_base}.zip"

                    sub_id = str(uuid.uuid4())
                    blob_name = f"batches/{org_id}/{batch_id}/{sub_id}_{student_name}.zip"

                    with open(student_zip_path, "rb") as f:
                        file_url = local_storage.save_file(f.read(), blob_name)

                    async with get_conn(org_id) as conn:
                        await conn.execute(
                            """
                            INSERT INTO submissions
                              (id, org_id, assignment_id, subject_id, batch_id,
                               type, mode, stdin_text, file_url, file_name, student_name, status, created_at)
                            VALUES ($1,$2,$3,$4,$5,$6,'batch',$7,$8,$9,$10,'uploaded',$11)
                            """,
                            sub_id, org_id, assignment_id, subject_id, batch_id,
                            type, stdin_text, file_url, f"{student_name}.zip", student_name, now,
                        )
                    submission_ids.append(sub_id)

        finally:
            if 'tmp_zip_path' in locals() and os.path.exists(tmp_zip_path):
                os.remove(tmp_zip_path)

        # Queue batch grading
        celery_app.send_task("tasks.run_batch_grading", args=[batch_id, org_id])

        return {
            "batch_id": batch_id,
            "total_files": len(submission_ids),
            "message": f"Batch uploaded successfully. Queued {len(submission_ids)} students for grading.",
        }

    except HTTPException:
        raise
    except Exception as e:
        error_msg = f"Batch processing failed: {str(e)}\n{traceback.format_exc()}"
        logger.error(error_msg)
        raise HTTPException(400, error_msg)


# ---- Batch name confirmation + processing trigger ---------------------------

class ConfirmNamesPayload(BaseModel):
    names: dict  # { submission_id: corrected_student_name }

@router.post("/batch/{batch_id}/confirm-names")
async def confirm_batch_names(
    batch_id: str,
    payload: ConfirmNamesPayload,
    user: dict = Depends(_get_instructor),
):
    """Update student names in submissions after the instructor reviews them."""
    org_id = str(user["org_id"])
    now = datetime.now(timezone.utc)
    async with get_conn(org_id) as conn:
        for sub_id, name in payload.names.items():
            await conn.execute(
                "UPDATE submissions SET student_name = $1 WHERE id = $2 AND batch_id = $3",
                name, sub_id, batch_id,
            )
    return {"status": "names_updated", "count": len(payload.names)}


@router.post("/batch/{batch_id}/process")
async def process_batch(batch_id: str, user: dict = Depends(_get_instructor)):
    """Trigger grading for an already-uploaded batch (called after name confirmation)."""
    org_id = str(user["org_id"])
    async with get_conn(org_id) as conn:
        row = await conn.fetchrow(
            "SELECT id FROM batches WHERE id = $1 AND instructor_id = $2",
            batch_id, user["uid"],
        )
    if not row:
        raise HTTPException(404, "Batch not found.")
    celery_app.send_task("tasks.run_batch_grading", args=[batch_id, org_id])
    return {"status": "processing_started", "batch_id": batch_id}


# ---- Batch status & reports -------------------------------------------------

@router.get("/batch/{batch_id}")
async def get_batch(batch_id: str, user: dict = Depends(_get_instructor)):
    async with get_conn(user["org_id"]) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM batches WHERE id = $1 AND instructor_id = $2",
            batch_id, user["uid"],
        )
    if not row:
        raise HTTPException(404, "Batch not found.")
    return dict(row)


class RenameBatchPayload(BaseModel):
    batch_name: str


@router.patch("/batch/{batch_id}/name")
async def rename_batch(
    batch_id: str,
    payload: RenameBatchPayload,
    user: dict = Depends(_get_instructor),
):
    """Rename a batch."""
    async with get_conn(user["org_id"]) as conn:
        result = await conn.execute(
            "UPDATE batches SET batch_name = $1 WHERE id = $2 AND instructor_id = $3",
            payload.batch_name, batch_id, user["uid"],
        )
    if result == "UPDATE 0":
        raise HTTPException(404, "Batch not found.")
    return {"status": "renamed", "batch_name": payload.batch_name}


@router.delete("/batch/{batch_id}")
async def delete_batch(
    batch_id: str,
    user: dict = Depends(_get_instructor),
):
    """Delete a batch and all its submissions/reports (CASCADE)."""
    async with get_conn(user["org_id"]) as conn:
        row = await conn.fetchrow(
            "SELECT id FROM batches WHERE id = $1 AND instructor_id = $2",
            batch_id, user["uid"],
        )
        if not row:
            raise HTTPException(404, "Batch not found.")
        await conn.execute("DELETE FROM batches WHERE id = $1", batch_id)
    return {"status": "deleted", "batch_id": batch_id}


@router.get("/batch/{batch_id}/reports")
async def list_batch_reports(batch_id: str, user: dict = Depends(_get_instructor)):
    async with get_conn(user["org_id"]) as conn:
        rows = await conn.fetch(
            """
            SELECT s.id as submission_id, s.file_name, s.student_name, s.status as submission_status,
                   fr.id as report_id, fr.ai_overall_score, fr.ai_max_score, fr.ai_status,
                   fr.ai_overall_confidence, fr.final_status,
                   fr.approved_at, fr.published_at, fr.was_edited
            FROM submissions s
            LEFT JOIN feedback_reports fr ON s.id = fr.submission_id
            WHERE s.batch_id = $1
            ORDER BY s.student_name ASC
            """,
            batch_id,
        )
    return {"reports": [dict(r) for r in rows]}


# ---- Approve a report -------------------------------------------------------

@router.get("/reports/{report_id}")
async def get_report_detail(
    report_id: str,
    user: dict = Depends(_get_instructor)
):
    """
    Fetch the full details of a specific feedback report, including AI payload.
    """
    async with get_conn(user["org_id"]) as conn:
        report = await conn.fetchrow(
            "SELECT id, submission_id, batch_id, ai_overall_score, ai_max_score, ai_payload, final_payload FROM feedback_reports WHERE id = $1",
            report_id
        )
        if not report:
            raise HTTPException(404, "Report not found.")
            
    return dict(report)

class ApprovePayload(BaseModel):
    final_payload: Optional[dict] = None   # If None, use AI payload as-is


@router.post("/batch/{batch_id}/reports/{report_id}/approve")
async def approve_report(
    batch_id: str,
    report_id: str,
    payload: ApprovePayload,
    user: dict = Depends(_get_instructor),
):
    """
    Instructor approves (and optionally edits) the AI grade.
    Sets approved_at. Students can see the report only after published_at is set.
    """
    now = datetime.now(timezone.utc)
    org_id = user["org_id"]

    async with get_conn(org_id) as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM feedback_reports WHERE id = $1 AND batch_id = $2",
            report_id, batch_id,
        )
        if not existing:
            raise HTTPException(404, "Report not found.")

        was_edited = payload.final_payload is not None
        final_payload = payload.final_payload or existing["ai_payload"]

        # Compute final score from final_payload (Python does the math)
        rubric_scores = final_payload.get("rubricScores", [])
        final_score = sum(s.get("score", 0) for s in rubric_scores)
        max_score = sum(s.get("maxScore", 0) for s in rubric_scores)

        await conn.execute(
            """
            UPDATE feedback_reports SET
              approved_by = $1, approved_at = $2, published_at = $2,
              final_payload = $3, final_overall_score = $4, final_max_score = $5,
              final_status = CASE WHEN $4 >= $5 * 0.5 THEN 'pass' ELSE 'fail' END,
              was_edited = $6
            WHERE id = $7
            """,
            user["uid"], now,
            final_payload if was_edited else existing["ai_payload"],
            final_score, max_score, was_edited,
            report_id,
        )

        # Update submission status
        await conn.execute(
            "UPDATE submissions SET status = 'published' WHERE id = $1",
            existing["submission_id"],
        )

        # Update batch approved_count
        await conn.execute(
            "UPDATE batches SET approved_count = approved_count + 1 WHERE id = $1",
            batch_id,
        )

    return {"status": "approved", "report_id": report_id, "was_edited": was_edited}


# ---- Export Batch Reports ---------------------------------------------------

@router.get("/batch/{batch_id}/export/excel")
async def export_batch_excel(batch_id: str, user: dict = Depends(_get_instructor)):
    import io
    import openpyxl
    from fastapi.responses import StreamingResponse

    async with get_conn(user["org_id"]) as conn:
        batch = await conn.fetchrow("SELECT * FROM batches WHERE id = $1 AND instructor_id = $2", batch_id, user["uid"])
        if not batch:
            raise HTTPException(404, "Batch not found.")
            
        reports = await conn.fetch("""
            SELECT s.student_name, s.file_name, fr.final_overall_score, fr.final_max_score, fr.final_status
            FROM feedback_reports fr
            JOIN submissions s ON s.id = fr.submission_id
            WHERE fr.batch_id = $1 AND fr.published_at IS NOT NULL
        """, batch_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Batch Grades"
    ws.append(["Student Name", "File Name", "Final Score", "Max Score", "Status", "Percentage"])
    
    for r in reports:
        pct = (r["final_overall_score"] / r["final_max_score"]) if r["final_max_score"] else 0
        ws.append([
            r["student_name"], 
            r["file_name"], 
            r["final_overall_score"], 
            r["final_max_score"], 
            r["final_status"],
            f"{pct*100:.1f}%"
        ])

    stream = io.BytesIO()
    wb.save(stream)
    stream.seek(0)
    
    return StreamingResponse(
        stream, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=Batch_Grades_{batch_id}.xlsx"}
    )


@router.get("/batch/{batch_id}/export/zip")
async def export_batch_zip(batch_id: str, user: dict = Depends(_get_instructor)):
    import io
    import zipfile
    from fastapi.responses import StreamingResponse
    import json

    async with get_conn(user["org_id"]) as conn:
        batch = await conn.fetchrow("SELECT * FROM batches WHERE id = $1 AND instructor_id = $2", batch_id, user["uid"])
        if not batch:
            raise HTTPException(404, "Batch not found.")
            
        reports = await conn.fetch("""
            SELECT s.student_name, fr.final_overall_score, fr.final_payload
            FROM feedback_reports fr
            JOIN submissions s ON s.id = fr.submission_id
            WHERE fr.batch_id = $1 AND fr.published_at IS NOT NULL
        """, batch_id)

    zip_stream = io.BytesIO()
    with zipfile.ZipFile(zip_stream, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in reports:
            # For MVP, we generate text-based summaries instead of heavy PDF rendering
            student_name = r["student_name"].replace(" ", "_")
            content = f"Feedback Report for {r['student_name']}\n"
            content += f"Final Score: {r['final_overall_score']}\n\n"
            
            payload = r["final_payload"] or {}
            rubrics = payload.get("rubricScores", [])
            for rub in rubrics:
                content += f"Criterion: {rub.get('criterionId', 'Unknown')}\n"
                content += f"Score: {rub.get('score', 0)}/{rub.get('maxScore', 0)}\n"
                content += f"Feedback: {rub.get('feedback', '')}\n\n"
                
            zf.writestr(f"{student_name}_feedback.txt", content)

    zip_stream.seek(0)
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=Batch_Reports_{batch_id}.zip"}
    )


# ---- Faculty Verification Application (from InstructorDashboard) ------------

@router.post("/faculty-application")
async def submit_faculty_application(
    fullName: str = Form(...),
    university: str = Form(...),
    department: str = Form(""),
    designation: str = Form(""),
    officialEmail: str = Form(...),
    proofFile: Optional[UploadFile] = File(None),
    uid: str = Depends(_get_verified_uid),
):
    """
    Instructor submits a faculty verification application.
    Uploads proof file to Firebase Storage and inserts a faculty_applications row.
    """
    now = datetime.now(timezone.utc)

    # Get org_id bypassing RLS
    async with get_conn() as conn:
        org_id_val = await conn.fetchval("SELECT get_user_org_id($1)", uid)
    if not org_id_val:
        raise HTTPException(404, "User not found.")
    org_id = str(org_id_val)

    # Upload proof file to Firebase Storage if provided
    proof_url = None
    if proofFile and proofFile.filename:
        try:
            content = await proofFile.read()
            blob_path = f"faculty_proofs/{uid}/{uuid.uuid4()}_{proofFile.filename}"
            proof_url = local_storage.save_file(content, blob_path)
        except Exception as e:
            logger.warning(f"Proof file upload failed: {e}")

    async with get_conn(org_id) as conn:
        # Prevent duplicate pending applications
        existing = await conn.fetchrow(
            "SELECT id FROM faculty_applications WHERE user_id = $1 AND status = 'pending'",
            uid
        )
        if existing:
            raise HTTPException(400, "You already have a pending application under review.")

        await conn.execute(
            """
            INSERT INTO faculty_applications
              (org_id, user_id, full_name, university, department, designation,
               official_email, proof_file_url, status)
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, 'pending')
            """,
            org_id, uid, fullName, university, department,
            designation, officialEmail, proof_url,
        )
        await conn.execute(
            "UPDATE users SET faculty_status = 'pending', updated_at = $1 WHERE uid = $2",
            now, uid,
        )

    return {"status": "submitted", "message": "Application submitted. An admin will review it shortly."}

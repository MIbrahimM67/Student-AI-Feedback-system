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
        return verify_id_token(token)["uid"]
    except Exception as e:
        raise HTTPException(401, str(e)) from e


async def _get_instructor(uid: str = Depends(_get_verified_uid)) -> dict:
    async with get_conn() as conn:
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

    # Upload to Firebase Storage
    blob_name = f"references/{org_id}/{subject_id}/{ref_id}_{file.filename}"
    try:
        bucket = get_storage_bucket()
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(file.filename)[1]
        ) as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        blob = bucket.blob(blob_name)
        blob.upload_from_filename(tmp_path)
        blob.make_public()
        file_url = blob.public_url
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

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
        
    bucket = get_storage_bucket()
    blob_name = f"submissions/{org_id}/{assignment_id}/{sub_id}_{file.filename}"
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
        
    try:
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(tmp_path)
        blob.make_public()
        file_url = blob.public_url
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
            
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
    plagiarism_enabled: bool = Form(False),
    type: str = Form("text"),
    stdin_text: Optional[str] = Form(None),
    file: UploadFile = File(...),
    user: dict = Depends(_get_instructor),
):
    from app.config import settings

    org_id = user["org_id"]
    uid = user["uid"]

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
               plagiarism_enabled, status, total_files, processed_files, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,'uploaded',0,0,$7)
            """,
            batch_id, org_id, uid, subject_id, assignment_id,
            plagiarism_enabled, now,
        )

    total_size = 0
    submission_ids = []
    bucket = get_storage_bucket()

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

                blob = bucket.blob(blob_name)
                blob.upload_from_filename(student_zip_path)
                blob.make_public()
                file_url = blob.public_url

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
        if os.path.exists(tmp_zip_path):
            os.remove(tmp_zip_path)

    # Queue batch grading
    celery_app.send_task("tasks.run_batch_grading", args=[batch_id, org_id])

    return {
        "batch_id": batch_id,
        "total_files": len(submission_ids),
        "message": f"Batch uploaded successfully. Queued {len(submission_ids)} students for grading.",
    }


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


@router.get("/batch/{batch_id}/reports")
async def list_batch_reports(batch_id: str, user: dict = Depends(_get_instructor)):
    async with get_conn(user["org_id"]) as conn:
        rows = await conn.fetch(
            """
            SELECT fr.id, fr.submission_id, s.file_name, s.student_name,
                   fr.ai_overall_score, fr.ai_max_score, fr.ai_status,
                   fr.ai_overall_confidence, fr.final_status,
                   fr.approved_at, fr.published_at, fr.was_edited
            FROM feedback_reports fr
            JOIN submissions s ON s.id = fr.submission_id
            WHERE fr.batch_id = $1
            ORDER BY fr.ai_overall_confidence ASC
            """,
            batch_id,
        )
    return {"reports": [dict(r) for r in rows]}


# ---- Approve a report -------------------------------------------------------

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

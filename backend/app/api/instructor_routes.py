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

from app.auth.firebase import DemoAccessDenied, verify_id_token
from app.services import file_storage
from app.services.demo_limits import check_submission_type, read_upload
from app.db.postgres import get_conn
from app.services.task_dispatch import dispatch, notify
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- Auth dependency --------------------------------------------------------

async def _get_verified_uid(authorization: Annotated[str, Header()]) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        return verify_id_token(token)["uid"]
    except DemoAccessDenied as e:
        raise HTTPException(403, str(e)) from e
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
    uid = user["uid"]
    ref_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    async with get_conn(str(org_id)) as conn:
        owned = await conn.fetchval("SELECT id FROM subjects WHERE id=$1 AND instructor_id=$2", subject_id, uid)
    if not owned:
        raise HTTPException(404, "Subject not found.")
    content = await read_upload(file)
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > 50:
        raise HTTPException(413, "Reference file must be under 50MB.")

    # Upload to Local Storage
    blob_name = f"references/{org_id}/{subject_id}/{ref_id}_{file.filename}"
    try:
        file_url = await file_storage.save_file(content, blob_name, org_id=org_id, owner_uid=uid)
    except HTTPException:
        raise
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

        await dispatch("tasks.index_reference_material", [ref_id, org_id, subject_id], conn=conn)
    notify()
    if not settings.DOCUMENT_DEMO:
        await dispatch("tasks.index_reference_material", [ref_id, org_id, subject_id])

    return {
        "reference_id": ref_id,
        "status": "pending",
        "message": "File uploaded. Indexing started — knowledge base will be ready when queued indexing completes.",
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
            SELECT id, title, type, index_status, index_method, chunk_count, created_at
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
    minimum_marks: Optional[int] = 0
    total_marks: Optional[int] = 100
    plagiarism_enabled: Optional[bool] = False
    internal_similarity_enabled: Optional[bool] = True
    internet_plagiarism_enabled: Optional[bool] = False
    use_subject_kb: Optional[bool] = True
    course_material_weight: Optional[int] = 60


class UpdateAssignmentRequest(BaseModel):
    title: str
    prompt: Optional[str] = ""
    rubric: Optional[str] = ""
    minimum_marks: Optional[int] = 0
    total_marks: Optional[int] = 100
    internal_similarity_enabled: Optional[bool] = True
    internet_plagiarism_enabled: Optional[bool] = False
    use_subject_kb: Optional[bool] = True
    course_material_weight: Optional[int] = 60

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
    rubric = (body.rubric or "").strip()
    plagiarism = bool(body.internal_similarity_enabled) or (not settings.DOCUMENT_DEMO and bool(body.internet_plagiarism_enabled))
    internal_similarity = bool(body.internal_similarity_enabled)
    internet_plagiarism = not settings.DOCUMENT_DEMO and bool(body.internet_plagiarism_enabled)
    use_subject_kb = bool(body.use_subject_kb)
    course_weight = max(0, min(100, int(body.course_material_weight or 0)))
    ai_weight = 100 - course_weight
    total_marks = max(1, int(body.total_marks or 100))
    minimum_marks = max(0, min(total_marks, int(body.minimum_marks or 0)))
    
    now = datetime.now(timezone.utc)

    async with get_conn(org_id) as conn:
        # Create assignment
        assignment_row = await conn.fetchrow(
            """
            INSERT INTO assignments (
              org_id, subject_id, title, plagiarism_enabled,
              internal_similarity_enabled, internet_plagiarism_enabled,
              minimum_marks, total_marks,
              use_subject_kb, course_material_weight, ai_expertise_weight,
              created_at
            )
            VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            RETURNING id
            """,
            org_id, subject_id, title, plagiarism,
            internal_similarity, internet_plagiarism,
            minimum_marks, total_marks, use_subject_kb, course_weight, ai_weight,
            now,
        )
        assignment_id = assignment_row["id"]
        
        # Save prompt as a single question
        if prompt:
            await conn.execute(
                """
                INSERT INTO questions (org_id, assignment_id, text, max_marks, display_order)
                VALUES ($1, $2, $3, $4, 0)
                """,
                org_id, assignment_id, prompt, total_marks
            )
            
        if not rubric:
            rubric = await _generate_default_rubric(title=title, prompt=prompt or "")

        await conn.execute(
            """
            INSERT INTO rubric_criteria (org_id, assignment_id, name, max_score, description)
            VALUES ($1, $2, $3, $4, $5)
            """,
            org_id,
            assignment_id,
            "Instructor Rubric" if body.rubric else "AI Generated Rubric",
            total_marks,
            rubric,
        )
            
        # Update assignment count
        await conn.execute(
            "UPDATE subjects SET assignment_count = assignment_count + 1, updated_at = $1 WHERE id = $2::uuid",
            now, subject_id,
        )

    return {"id": str(assignment_id), "message": "Assignment created successfully."}


@router.patch("/assignments/{assignment_id}")
async def update_assignment(
    assignment_id: str,
    body: UpdateAssignmentRequest,
    user: dict = Depends(_get_instructor),
):
    org_id = user["org_id"]
    title = body.title.strip()
    if not title:
        raise HTTPException(400, "Assignment title is required.")

    prompt = (body.prompt or "").strip()
    rubric = (body.rubric or "").strip()
    total_marks = max(1, int(body.total_marks or 100))
    minimum_marks = max(0, min(total_marks, int(body.minimum_marks or 0)))
    internal_similarity = bool(body.internal_similarity_enabled)
    internet_plagiarism = not settings.DOCUMENT_DEMO and bool(body.internet_plagiarism_enabled)
    plagiarism = internal_similarity or internet_plagiarism
    use_subject_kb = bool(body.use_subject_kb)
    course_weight = max(0, min(100, int(body.course_material_weight or 0)))
    ai_weight = 100 - course_weight

    if not rubric:
        rubric = await _generate_default_rubric(title=title, prompt=prompt)

    async with get_conn(org_id) as conn:
        row = await conn.fetchrow(
            "SELECT id FROM assignments WHERE id = $1::uuid AND org_id = $2",
            assignment_id,
            org_id,
        )
        if not row:
            raise HTTPException(404, "Assignment not found.")

        await conn.execute(
            """
            UPDATE assignments
            SET title = $1,
                plagiarism_enabled = $2,
                internal_similarity_enabled = $3,
                internet_plagiarism_enabled = $4,
                minimum_marks = $5,
                total_marks = $6,
                use_subject_kb = $7,
                course_material_weight = $8,
                ai_expertise_weight = $9,
                version = version + 1
            WHERE id = $10::uuid AND org_id = $11
            """,
            title,
            plagiarism,
            internal_similarity,
            internet_plagiarism,
            minimum_marks,
            total_marks,
            use_subject_kb,
            course_weight,
            ai_weight,
            assignment_id,
            org_id,
        )

        await conn.execute("DELETE FROM questions WHERE assignment_id = $1::uuid", assignment_id)
        await conn.execute("DELETE FROM rubric_criteria WHERE assignment_id = $1::uuid", assignment_id)

        if prompt:
            await conn.execute(
                """
                INSERT INTO questions (org_id, assignment_id, text, max_marks, display_order)
                VALUES ($1, $2::uuid, $3, $4, 0)
                """,
                org_id,
                assignment_id,
                prompt,
                total_marks,
            )

        await conn.execute(
            """
            INSERT INTO rubric_criteria (org_id, assignment_id, name, max_score, description)
            VALUES ($1, $2::uuid, $3, $4, $5)
            """,
            org_id,
            assignment_id,
            "Instructor Rubric" if body.rubric else "AI Generated Rubric",
            total_marks,
            rubric,
        )

    return {"id": assignment_id, "message": "Assignment updated successfully."}


async def _generate_default_rubric(title: str, prompt: str) -> str:
    from app.services.llm_provider import ChatMessage, build_llm_from_env

    fallback = (
        "Evaluate the submission using: 40% correctness and coverage of the task, "
        "25% depth and technical accuracy, 20% organization and clarity, "
        "15% examples, justification, and completeness."
    )
    try:
        llm = build_llm_from_env()
        resp = await llm.chat(
            messages=[
                ChatMessage(
                    role="system",
                    content=(
                        "You create concise academic grading rubrics. "
                        "Return only the rubric text, with weighted criteria that sum to 100%."
                    ),
                ),
                ChatMessage(
                    role="user",
                    content=(
                        f"Assignment title: {title}\n"
                        f"Assignment prompt: {prompt or 'No prompt provided.'}\n\n"
                        "Create a fair grading rubric/evaluation criteria for this assignment."
                    ),
                ),
            ],
            model=settings.GRADIENT_MODEL_UTILITY,
            temperature=0.2,
            max_tokens=500,
        )
        return resp.text.strip() or fallback
    except Exception as e:
        logger.warning("Default rubric generation failed: %s", e)
        return fallback


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
    check_submission_type(type)
    org_id = user["org_id"]
    uid = user["uid"]
    
    sub_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    
    content = await read_upload(file, kind=type)
    if len(content) > settings.STUDENT_MAX_FILE_MB * 1024 * 1024:
        raise HTTPException(413, f"File exceeds {settings.STUDENT_MAX_FILE_MB}MB limit.")
        
    blob_name = f"submissions/{org_id}/{assignment_id}/{sub_id}_{file.filename}"
    try:
        file_url = await file_storage.save_file(content, blob_name, org_id=org_id, owner_uid=uid, kind=type)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Local storage upload failed: %s", e)
        raise HTTPException(500, f"File upload failed: {e}")
            
    try:
        async with get_conn(org_id) as conn:
            batch_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO batches
                  (id, org_id, instructor_id, subject_id, assignment_id,
                   batch_name, plagiarism_enabled, status, total_files, processed_files, created_at)
                VALUES ($1,$2,$3,$4,$5,$6,$7,'uploaded',0,0,$8)
                """,
                batch_id, org_id, uid, subject_id, assignment_id,
                f"{student_name} (Single)", plagiarism_enabled, now,
            )

            await conn.execute(
                """
                INSERT INTO submissions 
                  (id, org_id, assignment_id, subject_id, batch_id, type, mode, stdin_text, file_url, file_name, status, student_name, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, 'single', $7, $8, $9, 'uploaded', $10, $11)
                """,
                sub_id, org_id, assignment_id, subject_id, batch_id, type, stdin_text, file_url, file.filename, student_name, now,
            )
            
            await dispatch("tasks.grade_submission", [sub_id, org_id], conn=conn)

            # Increment the batch total files count
            await conn.execute(
                "UPDATE batches SET total_files = total_files + 1 WHERE id = $1", batch_id
            )
    except Exception as e:
        logger.error("DB Insert Failed: %s", e)
        raise HTTPException(status_code=400, detail=f"Database error: {str(e)}")
        
    notify()
    if not settings.DOCUMENT_DEMO:
        await dispatch("tasks.grade_submission", [sub_id, org_id])
    
    return {
        "submission_id": sub_id,
        "batch_id": batch_id,
        "status": "pending",
        "message": f"Submission for {student_name} uploaded. Grading started."
    }

def _clean_extracted_student_name(raw_name: str) -> str:
    """
    Cleans raw folder or file names into a clean readable student name.
    e.g. '21k-1234_John_Doe' -> 'John Doe'
    'student_01_jane_doe.pdf' -> 'Jane Doe'
    'CS101 - Alex Smith (Final)' -> 'Alex Smith'
    """
    import re
    name = os.path.splitext(raw_name)[0]
    # Strip common prefixes like rolls, IDs, student_
    name = re.sub(r'^(student[_\-\s]*|\d+[_\-\s]*|[a-zA-Z]{1,4}\d+[_\-\s]*)', '', name, flags=re.IGNORECASE)
    # Replace underscores and hyphens with spaces
    name = re.sub(r'[_\-]+', ' ', name).strip()
    # Strip parenthesized suffixes like (1), (Final)
    name = re.sub(r'\s*\([^)]*\)$', '', name).strip()
    # Title-case words
    cleaned = ' '.join(word.capitalize() for word in name.split())
    return cleaned if cleaned else raw_name


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
    from app.services.batch_ingestion import stage_archive
    from pathlib import PurePosixPath
    org_id = str(user["org_id"])
    check_submission_type(type)
    batch_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    async with get_conn(org_id) as conn:
        owned = await conn.fetchrow(
            "SELECT a.id FROM assignments a JOIN subjects s ON s.id=a.subject_id "
            "WHERE a.id=$1 AND a.subject_id=$2 AND s.instructor_id=$3",
            assignment_id, subject_id, user["uid"],
        )
    if not owned:
        raise HTTPException(404, "Assignment not found in this classroom.")
    async with stage_archive(file, type) as entries:
        staged = []
        # One transaction owns the files, storage reservation and all submission rows.
        async with get_conn(org_id) as conn:
            await conn.execute(
                "INSERT INTO batches(id,org_id,instructor_id,subject_id,assignment_id,batch_name,"
                "plagiarism_enabled,status,total_files,processed_files,created_at) "
                "VALUES($1,$2,$3,$4,$5,$6,$7,'uploaded',$8,0,$9)",
                batch_id, org_id, user["uid"], subject_id, assignment_id,
                batch_name or f"Batch {now.strftime('%b %d, %H:%M')}", plagiarism_enabled, len(entries), now,
            )
            for entry in entries:
                sub_id = str(uuid.uuid4())
                filename = entry["filename"]
                archive_name = PurePosixPath(entry["archive_name"])
                raw_name = archive_name.parent.name if len(archive_name.parts) > 2 else filename
                name = _clean_extracted_student_name(raw_name)
                url = await file_storage.save_file(
                    entry["path"].read_bytes(), f"batches/{org_id}/{batch_id}/{sub_id}_{filename}",
                    org_id=org_id, owner_uid=user["uid"], kind=type, conn=conn,
                )
                await conn.execute(
                    "INSERT INTO submissions(id,org_id,assignment_id,subject_id,batch_id,type,mode,"
                    "stdin_text,file_url,file_name,student_name,status,created_at) "
                    "VALUES($1,$2,$3,$4,$5,$6,'batch',$7,$8,$9,$10,'uploaded',$11)",
                    sub_id, org_id, assignment_id, subject_id, batch_id, type, stdin_text, url, filename, name, now,
                )
                staged.append({"submissionId":sub_id,"fileName":entry["archive_name"],"extractedName":name})
    return {"batch_id":batch_id,"total_files":len(staged),"students":staged,
            "message":f"Staged {len(staged)} submissions. Review names, then start grading."}


# ---- Batch name confirmation + processing trigger ---------------------------

class ConfirmNamesPayload(BaseModel):
    names: Any  # Can be dict { submission_id: name } or list [{ submissionId, studentName }]

@router.post("/batch/{batch_id}/confirm-names")
async def confirm_batch_names(
    batch_id: str,
    payload: ConfirmNamesPayload,
    user: dict = Depends(_get_instructor),
):
    """Update student names in submissions after the instructor reviews them."""
    org_id = str(user["org_id"])
    names_dict = {}

    if isinstance(payload.names, dict):
        names_dict = payload.names
    elif isinstance(payload.names, list):
        for item in payload.names:
            if isinstance(item, dict):
                sub_id = item.get("submissionId") or item.get("submission_id")
                name = item.get("studentName") or item.get("student_name")
                if sub_id and name:
                    names_dict[str(sub_id)] = str(name).strip()

    async with get_conn(org_id) as conn:
        for sub_id, name in names_dict.items():
            await conn.execute(
                "UPDATE submissions SET student_name = $1 WHERE id = $2 AND batch_id = $3",
                name, sub_id, batch_id,
            )
    return {"status": "names_updated", "count": len(names_dict)}


@router.post("/batch/{batch_id}/process")
async def process_batch(batch_id: str, user: dict = Depends(_get_instructor)):
    """Trigger grading for an already-uploaded batch (called after name confirmation)."""
    from app.services.batch_ingestion import batch_file_limit
    org_id = str(user["org_id"])
    submission_ids = []
    async with get_conn(org_id) as conn:
        row = await conn.fetchrow("SELECT id,status FROM batches WHERE id=$1 AND instructor_id=$2 FOR UPDATE", batch_id, user["uid"])
        if not row:
            raise HTTPException(404, "Batch not found.")
        if row["status"] != "uploaded":
            return {"status":row["status"],"batch_id":batch_id}
        rows = await conn.fetch("SELECT id FROM submissions WHERE batch_id=$1 AND status='uploaded' ORDER BY created_at,id", batch_id)
        if not 1 <= len(rows) <= batch_file_limit():
            raise HTTPException(400, f"A batch must contain 1-{batch_file_limit()} unprocessed submissions.")
        await conn.execute("UPDATE batches SET status='processing' WHERE id=$1", batch_id)
        for row in rows:
            submission_ids.append(str(row["id"]))
            await dispatch("tasks.grade_submission", [str(row["id"]),org_id], conn=conn)
    notify()
    if not settings.DOCUMENT_DEMO:
        for sid in submission_ids:
            await dispatch("tasks.grade_submission", [sid,org_id])
    return {"status":"processing_started","batch_id":batch_id,"total_files":len(submission_ids)}



class UpdateStudentNamePayload(BaseModel):
    student_name: str

@router.patch("/submissions/{submission_id}/student-name")
async def update_submission_student_name(
    submission_id: str,
    payload: UpdateStudentNamePayload,
    user: dict = Depends(_get_instructor),
):
    """Allows instructors to edit a student's name on a submission at any time."""
    org_id = str(user["org_id"])
    new_name = payload.student_name.strip()
    if not new_name:
        raise HTTPException(400, "Student name cannot be empty.")
    async with get_conn(org_id) as conn:
        res = await conn.execute(
            "UPDATE submissions SET student_name = $1 WHERE id = $2",
            new_name, submission_id
        )
    return {"status": "success", "submission_id": submission_id, "student_name": new_name}


# ---- Batch status & reports -------------------------------------------------

@router.get("/batch/{batch_id}")
async def get_batch(batch_id: str, user: dict = Depends(_get_instructor)):
    async with get_conn(user["org_id"]) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM batches WHERE id = $1 AND instructor_id = $2",
            batch_id, user["uid"],
        )
        stats = await conn.fetchrow(
            """
            SELECT
              COUNT(*)::int AS submission_count,
              COUNT(*) FILTER (WHERE status = 'uploaded')::int AS queued_count,
              COUNT(*) FILTER (WHERE status = 'processing')::int AS active_count,
              COUNT(*) FILTER (WHERE status IN ('graded','approved','published'))::int AS graded_count,
              COUNT(*) FILTER (WHERE status = 'failed')::int AS failed_count,
              COALESCE(ROUND(AVG(
                CASE
                  WHEN status IN ('graded','approved','published','failed') THEN 100
                  ELSE COALESCE(progress_percent, 0)
                END
              )), 0)::int AS progress_percent
            FROM submissions
            WHERE batch_id = $1
            """,
            batch_id,
        )
        active = await conn.fetchrow(
            """
            SELECT progress_stage, progress_message, progress_updated_at
            FROM submissions
            WHERE batch_id = $1 AND status IN ('uploaded','processing')
            ORDER BY progress_updated_at DESC NULLS LAST, created_at ASC
            LIMIT 1
            """,
            batch_id,
        )
    if not row:
        raise HTTPException(404, "Batch not found.")

    data = dict(row)
    if stats:
        data.update(dict(stats))
    if active:
        data["active_stage"] = active["progress_stage"] or "queued"
        data["progress_message"] = active["progress_message"] or "Waiting for the grading worker to start."
        data["progress_updated_at"] = active["progress_updated_at"]
    elif data.get("total_files"):
        failed = data.get("failed_count", 0)
        data["active_stage"] = "failed" if failed else "completed"
        data["progress_message"] = (
            f"Grading finished with {failed} failed submission(s). Upload those files again to retry."
            if failed else "All submissions have completed AI processing."
        )
        data["progress_percent"] = 100
    else:
        data["active_stage"] = "uploaded"
        data["progress_message"] = "Batch uploaded."
    return data


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
                   s.progress_stage, s.progress_percent, s.progress_message, s.progress_updated_at,
                   fr.id as report_id, fr.ai_overall_score, fr.ai_max_score, fr.ai_status,
                   fr.ai_overall_confidence, fr.final_status,
                   fr.approved_at, fr.published_at, fr.was_edited,
                   pr.similarity_score as plagiarism_similarity_score,
                   pr.matches as plagiarism_matches
            FROM submissions s
            LEFT JOIN feedback_reports fr ON s.id = fr.submission_id
            LEFT JOIN LATERAL (
              SELECT similarity_score, matches
              FROM plagiarism_reports
              WHERE submission_id = s.id
              ORDER BY created_at DESC
              LIMIT 1
            ) pr ON true
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
    import json
    async with get_conn(user["org_id"]) as conn:
        report = await conn.fetchrow(
            """
            SELECT fr.id, fr.submission_id, fr.batch_id, fr.ai_overall_score, fr.ai_max_score,
                   fr.ai_payload, fr.final_payload,
                   pr.similarity_score as plagiarism_similarity_score,
                   pr.matches as plagiarism_matches
            FROM feedback_reports fr
            LEFT JOIN LATERAL (
              SELECT similarity_score, matches
              FROM plagiarism_reports
              WHERE submission_id = fr.submission_id
              ORDER BY created_at DESC
              LIMIT 1
            ) pr ON true
            WHERE fr.id = $1
            """,
            report_id
        )
        if not report:
            raise HTTPException(404, "Report not found.")
            
        r_dict = dict(report)
        if isinstance(r_dict.get("ai_payload"), str):
            r_dict["ai_payload"] = json.loads(r_dict["ai_payload"])
        if isinstance(r_dict.get("final_payload"), str):
            r_dict["final_payload"] = json.loads(r_dict["final_payload"])
        if isinstance(r_dict.get("plagiarism_matches"), str):
            r_dict["plagiarism_matches"] = json.loads(r_dict["plagiarism_matches"])
            
    return r_dict

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
    import json
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
        # Parse ai_payload if it's a string from asyncpg
        ai_payload = existing["ai_payload"]
        if isinstance(ai_payload, str):
            ai_payload = json.loads(ai_payload)

        final_payload = payload.final_payload or ai_payload

        # Compute final score from final_payload (Python does the math)
        final_score = 0
        max_score = existing["ai_max_score"]
        if "per_criterion" in final_payload and isinstance(final_payload["per_criterion"], dict):
            final_score = sum(
                float(s["score"] if isinstance(s, dict) else s)
                for s in final_payload["per_criterion"].values()
            )
        else:
            final_score = existing["ai_overall_score"] or 0

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
            json.dumps(final_payload) if isinstance(final_payload, dict) else final_payload,
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
            SELECT s.student_name, s.file_name, 
                   COALESCE(fr.final_overall_score, fr.ai_overall_score) as score, 
                   COALESCE(fr.final_max_score, fr.ai_max_score) as max_score, 
                   COALESCE(fr.final_status, fr.ai_status) as status
            FROM feedback_reports fr
            JOIN submissions s ON s.id = fr.submission_id
            WHERE fr.batch_id = $1
        """, batch_id)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Batch Grades"
    ws.append(["Student Name", "File Name", "Final Score", "Max Score", "Status", "Percentage"])
    
    for r in reports:
        score = r["score"] or 0
        max_score = r["max_score"] or 0
        pct = (score / max_score) if max_score else 0
        ws.append([
            r["student_name"], 
            r["file_name"], 
            score, 
            max_score, 
            r["status"],
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
    from app.services.report_service import report_service

    async with get_conn(user["org_id"]) as conn:
        batch = await conn.fetchrow(
            """
            SELECT b.*, a.title as assignment_title 
            FROM batches b 
            LEFT JOIN assignments a ON a.id = b.assignment_id 
            WHERE b.id = $1 AND b.instructor_id = $2
            """, 
            batch_id, user["uid"]
        )
        if not batch:
            raise HTTPException(404, "Batch not found.")
            
        reports = await conn.fetch(
            """
            SELECT s.id as submission_id, s.student_name, s.file_name, s.type as submission_type,
                   COALESCE(fr.final_overall_score, fr.ai_overall_score) as score,
                   COALESCE(fr.final_max_score, fr.ai_max_score) as max_score,
                   COALESCE(fr.final_status, fr.ai_status) as status,
                   COALESCE(fr.final_payload, fr.ai_payload) as payload,
                   pr.similarity_score as plagiarism_similarity_score
            FROM feedback_reports fr
            JOIN submissions s ON s.id = fr.submission_id
            LEFT JOIN plagiarism_reports pr ON pr.submission_id = s.id
            WHERE fr.batch_id = $1
            """, 
            batch_id
        )

    zip_stream = io.BytesIO()
    excel_records = []

    with zipfile.ZipFile(zip_stream, "w", zipfile.ZIP_DEFLATED) as zf:
        for r in reports:
            raw_payload = r["payload"]
            payload = {}
            if isinstance(raw_payload, str):
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    pass
            elif raw_payload:
                payload = dict(raw_payload)

            student_name = r["student_name"] or "Student"
            safe_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
            if not safe_name:
                safe_name = f"Student_{str(r['submission_id'])[:8]}"

            payload["score"] = r["score"] or 0
            payload["max_score"] = r["max_score"] or 100
            payload["status"] = r["status"] or "completed"
            if r["plagiarism_similarity_score"] is not None:
                payload["plagiarism_similarity_score"] = float(r["plagiarism_similarity_score"])

            try:
                pdf_bytes = report_service.generate_student_pdf_bytes(
                    report_data=payload,
                    student_name=student_name,
                    assignment_type=r["submission_type"] or "text",
                    file_name=r["file_name"] or "assignment",
                    assignment_title=batch["assignment_title"] or batch["batch_name"] or "Assignment",
                )
                zf.writestr(f"{safe_name}_Feedback_Report.pdf", pdf_bytes)
            except Exception as e:
                logger.error("Failed to generate PDF for %s: %s", student_name, e)
                md_text = f"# GradeWise Feedback: {student_name}\n\nScore: {r['score']}/{r['max_score']}\nStatus: {r['status']}\n\nSummary:\n{payload.get('summary', payload.get('student_feedback', ''))}"
                zf.writestr(f"{safe_name}_Feedback_Report.md", md_text)

            excel_records.append({
                "student_name": student_name,
                "file_name": r["file_name"] or "assignment",
                "score": r["score"] or 0,
                "max_score": r["max_score"] or 100,
                "status": r["status"] or "completed",
                "strengths": payload.get("strengths", []),
                "weaknesses": payload.get("weaknesses", []),
                "suggestions": payload.get("suggestions", []),
                "plagiarism_similarity_score": r["plagiarism_similarity_score"] or 0.0,
            })

        try:
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp_xlsx:
                tmp_xlsx_path = tmp_xlsx.name
            await report_service.generate_batch_excel(excel_records, tmp_xlsx_path)
            with open(tmp_xlsx_path, "rb") as f:
                zf.writestr("Batch_Grades_Overview.xlsx", f.read())
            if os.path.exists(tmp_xlsx_path):
                os.remove(tmp_xlsx_path)
        except Exception as e:
            logger.error("Failed to add Excel summary to zip: %s", e)

    zip_stream.seek(0)
    batch_title = "".join(c for c in (batch["batch_name"] or f"Batch_{batch_id[:8]}") if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    return StreamingResponse(
        zip_stream,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{batch_title}_PDF_Reports.zip"'}
    )


@router.get("/reports/{report_id}/pdf")
async def export_report_pdf(report_id: str, user: dict = Depends(_get_instructor)):
    from app.services.report_service import report_service
    from fastapi.responses import Response
    import json

    org_id = user["org_id"]
    async with get_conn(org_id) as conn:
        r = await conn.fetchrow(
            """
            SELECT fr.*, s.student_name, s.file_name, s.type as submission_type,
                   a.title as assignment_title,
                   COALESCE(fr.final_overall_score, fr.ai_overall_score) as score,
                   COALESCE(fr.final_max_score, fr.ai_max_score) as max_score,
                   COALESCE(fr.final_status, fr.ai_status) as status,
                   COALESCE(fr.final_payload, fr.ai_payload) as payload,
                   pr.similarity_score as plagiarism_similarity_score
            FROM feedback_reports fr
            JOIN submissions s ON s.id = fr.submission_id
            LEFT JOIN assignments a ON a.id = s.assignment_id
            LEFT JOIN plagiarism_reports pr ON pr.submission_id = s.id
            WHERE fr.id = $1
            """, 
            report_id
        )
        if not r:
            raise HTTPException(404, "Report not found.")

    raw_payload = r["payload"]
    payload = {}
    if isinstance(raw_payload, str):
        try:
            payload = json.loads(raw_payload)
        except Exception:
            pass
    elif raw_payload:
        payload = dict(raw_payload)

    payload["score"] = r["score"] or 0
    payload["max_score"] = r["max_score"] or 100
    payload["status"] = r["status"] or "completed"
    if r["plagiarism_similarity_score"] is not None:
        payload["plagiarism_similarity_score"] = float(r["plagiarism_similarity_score"])

    student_name = r["student_name"] or "Student"
    pdf_bytes = report_service.generate_student_pdf_bytes(
        report_data=payload,
        student_name=student_name,
        assignment_type=r["submission_type"] or "text",
        file_name=r["file_name"] or "assignment",
        assignment_title=r["assignment_title"] or "Assignment Submission",
    )

    safe_name = "".join(c for c in student_name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}_Feedback_Report.pdf"'}
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
            content = await read_upload(proofFile)
            blob_path = f"faculty_proofs/{uid}/{uuid.uuid4()}_{proofFile.filename}"
            proof_url = await file_storage.save_file(content, blob_path, org_id=org_id, owner_uid=uid)
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


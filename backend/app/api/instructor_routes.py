import os
import tempfile
import uuid
import logging
import zipfile
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, status
from pydantic import BaseModel
from backend.app.firebase import db, bucket
from backend.app.utils.security import get_current_user, require_instructor, require_pro
from backend.app.services.ocr_service import ocr_service
from backend.app.services.code_sandbox_service import code_sandbox_service
from backend.app.services.warning_service import warning_service
from backend.app.services.feedback_pipeline import feedback_pipeline
from backend.app.services.report_service import report_service
from backend.app.services.plagiarism_service import plagiarism_service
from backend.app.services.digitalocean_service import ai_service
from backend.app.config import settings

router = APIRouter(prefix="/api/instructor", tags=["Instructor Console"])
logger = logging.getLogger("instructor_routes")

class NameConfirmation(BaseModel):
    submissionId: str
    studentName: str

class ConfirmNamesRequest(BaseModel):
    names: List[NameConfirmation]

# --- FACULTY VERIFICATION APPLICATIONS ---

@router.post("/faculty-application")
async def apply_faculty_verification(
    fullName: str = Form(...),
    university: str = Form(...),
    department: str = Form(...),
    designation: str = Form(...),
    officialEmail: str = Form(...),
    proofFile: UploadFile = File(...),
    user: Dict[str, Any] = Depends(require_instructor)
):
    """
    Submits a verification form to upgrade an instructor account.
    Uploads document to Storage and creates a 'facultyApplications' record.
    """
    uid = user["uid"]
    app_id = f"app_{str(uuid.uuid4())[:8]}"
    
    try:
        # Save file to Firebase Storage
        proof_ext = os.path.splitext(proofFile.filename)[1]
        blob_name = f"faculty_proofs/{uid}_{app_id}{proof_ext}"
        blob = bucket.blob(blob_name)
        
        content = await proofFile.read()
        blob.upload_from_string(content, content_type=proofFile.content_type)
        proof_url = blob.generate_signed_url()
        
        # Save Firestore application
        app_data = {
            "id": app_id,
            "userId": uid,
            "fullName": fullName,
            "university": university,
            "department": department,
            "designation": designation,
            "officialEmail": officialEmail,
            "proofFileUrl": proof_url,
            "status": "pending",
            "rejectionReason": "",
            "reviewedBy": None,
            "createdAt": datetime.utcnow().isoformat(),
            "reviewedAt": None
        }
        db.collection("facultyApplications").document(app_id).set(app_data)
        
        # Update user status to pending
        db.collection("users").document(uid).update({
            "facultyStatus": "pending",
            "updatedAt": datetime.utcnow().isoformat()
        })
        
        return {"status": "submitted", "applicationId": app_id}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification upload failed: {e}"
        )

@router.get("/faculty-application/status")
async def get_faculty_status(user: Dict[str, Any] = Depends(require_instructor)):
    """
    Queries current verification process logs.
    """
    uid = user["uid"]
    apps = db.collection("facultyApplications").where("userId", "==", uid).stream()
    
    app_list = [doc.to_dict() for doc in apps]
    if not app_list:
        return {"status": "none"}
        
    # Return latest application
    app_list.sort(key=lambda x: x.get("createdAt", ""), reverse=True)
    return app_list[0]

# --- BATCH UPLOAD & AI GRADING PIPELINES (PRO FEATURE) ---

@router.post("/batch")
async def upload_batch_assignments(
    prompt: str = Form(...),
    rubric: Optional[str] = Form(""),
    plagiarismEnabled: bool = Form(True),
    type: str = Form("text"), # text | handwritten | coding
    files: List[UploadFile] = File(...),
    user: Dict[str, Any] = Depends(require_pro)
):
    """
    Substages a batch run containing up to 30 files (100MB limit).
    Runs Fast LLM classification to auto-extract student names for review.
    """
    uid = user["uid"]
    batch_id = f"batch_{str(uuid.uuid4())[:8]}"
    
    # 1. Enforce batch limits
    if len(files) > 30:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Instructor batch uploads are strictly limited to a maximum of 30 files."
        )
        
    total_size = 0
    staged_submissions = []
    
    try:
        for file in files:
            content = await file.read()
            total_size += len(content)
            
            # Enforce 100MB cap (104,857,600 bytes)
            if total_size > 104857600:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Batch upload size exceeds the maximum limit of 100MB."
                )
                
            sub_id = f"sub_{str(uuid.uuid4())[:8]}"
            file_name = file.filename
            
            # Save temporary files
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
                temp_file.write(content)
                temp_path = temp_file.name
                
            try:
                # Upload assignment files to storage bucket
                blob_name = f"batches/{batch_id}/{sub_id}_{file_name}"
                blob = bucket.blob(blob_name)
                blob.upload_from_filename(temp_path)
                file_url = blob.generate_signed_url()
                
                # Auto-extract text
                extracted_text = ""
                if type.lower() == "handwritten":
                    extracted_text = await ocr_service.extract_text(temp_path, file_name)
                elif type.lower() == "coding":
                    with open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
                        extracted_text = f.read()
                else:
                    if file_name.lower().endswith('.pdf'):
                        extracted_text = await ocr_service.extract_text(temp_path, file_name)
                    else:
                        with open(temp_path, "r", encoding="utf-8", errors="ignore") as f:
                            extracted_text = f.read()
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            
            # 2. Fast Model name extraction
            extracted_name = await _auto_extract_student_name(file_name, extracted_text[:800])
            
            staged_submissions.append({
                "id": sub_id,
                "userId": uid,
                "batchJobId": batch_id,
                "type": type,
                "mode": "batch",
                "inputText": extracted_text,
                "fileUrl": file_url,
                "fileName": file_name,
                "prompt": prompt,
                "rubric": rubric,
                "studentName": extracted_name,
                "status": "uploaded",
                "createdAt": datetime.utcnow().isoformat()
            })

        # Save batch state to db
        batch_data = {
            "id": batch_id,
            "instructorId": uid,
            "assignmentPrompt": prompt,
            "rubric": rubric,
            "plagiarismEnabled": plagiarismEnabled,
            "status": "uploaded",
            "totalFiles": len(files),
            "processedFiles": 0,
            "exportExcelUrl": "",
            "exportZipUrl": "",
            "createdAt": datetime.utcnow().isoformat()
        }
        db.collection("batchJobs").document(batch_id).set(batch_data)
        
        # Save submissions
        for sub in staged_submissions:
            db.collection("submissions").document(sub["id"]).set(sub)
            
        # Return names for editing confirm flow
        name_review_list = [{"submissionId": s["id"], "fileName": s["fileName"], "extractedName": s["studentName"]} for s in staged_submissions]
        
        return {
            "batchId": batch_id,
            "totalFiles": len(files),
            "nameReviewList": name_review_list
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to compile batch staging: {e}")
        raise HTTPException(status_code=500, detail=f"Batch initialization failed: {e}")

@router.get("/batch/{id}")
async def get_batch_job(id: str, user: Dict[str, Any] = Depends(require_pro)):
    """
    Checks batch progress indicators.
    """
    snap = db.collection("batchJobs").document(id).get()
    if not snap.exists:
        raise HTTPException(status_code=404, detail="Batch job not found.")
        
    data = snap.to_dict() or {}
    if data.get("instructorId") != user["uid"]:
        raise HTTPException(status_code=403, detail="Unprivileged access forbidden.")
    return data

@router.post("/batch/{id}/confirm-names")
async def confirm_student_names(id: str, payload: ConfirmNamesRequest, user: Dict[str, Any] = Depends(require_pro)):
    """
    Saves the finalized student names to their staging submission documents.
    """
    batch = await get_batch_job(id, user)
    
    try:
        for item in payload.names:
            sub_ref = db.collection("submissions").document(item.submissionId)
            sub_snap = sub_ref.get()
            if sub_snap.exists:
                sub_data = sub_snap.to_dict() or {}
                if sub_data.get("batchJobId") == id:
                    sub_ref.update({"studentName": item.studentName})
                    
        return {"status": "names_confirmed", "message": "Student names updated successfully. Ready to trigger processing."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to confirm student names: {e}")

@router.post("/batch/{id}/process")
async def process_batch_job(id: str, background_tasks: BackgroundTasks, user: Dict[str, Any] = Depends(require_pro)):
    """
    Launches bulk evaluation via non-blocking BackgroundTasks thread pools.
    """
    batch = await get_batch_job(id, user)
    if batch.get("status") in ["processing", "completed"]:
        return {"status": batch.get("status"), "message": f"Batch process already in state: {batch.get('status')}"}
        
    db.collection("batchJobs").document(id).update({
        "status": "processing",
        "processedFiles": 0
    })
    
    # Run the background grading process safely
    background_tasks.add_task(_background_batch_grading_routine, id, user["uid"])
    
    return {"status": "processing", "message": "Batch evaluation started successfully in background."}

@router.get("/batch/{id}/export")
async def export_batch_reports(id: str, user: Dict[str, Any] = Depends(require_pro)):
    """
    Gets links to aggregated reports.
    """
    batch = await get_batch_job(id, user)
    if batch.get("status") != "completed":
        raise HTTPException(status_code=400, detail="Batch execution is not finalized yet.")
        
    return {
        "exportExcelUrl": batch.get("exportExcelUrl"),
        "exportZipUrl": batch.get("exportZipUrl")
    }

# --- BULK BACKGROUND GRADERS & AI HELPERS ---

async def _auto_extract_student_name(filename: str, header_text: str) -> str:
    """
    Fast LLM prompt to identify a student name from the file header or filename.
    """
    try:
        prompt = (
            "Identify the student's name from this filename and assignment header snippet.\n"
            f"Filename: {filename}\n"
            f"Snippet: {header_text}\n\n"
            "Respond ONLY with the name itself (e.g. 'John Smith'). Do not write paragraphs or explanations. "
            "If absolutely no name is present, return 'Unknown Student'."
        )
        name_response = await ai_service.chat(
            messages=[{"role": "user", "content": prompt}],
            model=settings.DIGITALOCEAN_MODEL_FAST,
            temperature=0.1
        )
        name = name_response.strip().replace("Name:", "").replace("\"", "").replace("'", "")
        return name[:40] if name else "Unknown Student"
    except Exception:
        # Basic parsing backup
        clean_file = os.path.splitext(filename)[0].replace("_", " ").replace("-", " ")
        words = [w.capitalize() for w in clean_file.split() if w.lower() not in ["assignment", "homework", "hw", "submission", "student"]]
        return " ".join(words[:2]) if words else "Unknown Student"

async def _background_batch_grading_routine(batch_id: str, instructor_id: str):
    """
    Robust background task running sequentially through batch submissions.
    """
    logger.info(f"[Background Task] Staging batch grading routine: {batch_id}")
    
    try:
        # Load batch meta
        batch_ref = db.collection("batchJobs").document(batch_id)
        batch = batch_ref.get().to_dict() or {}
        
        prompt = batch.get("assignmentPrompt", "")
        rubric = batch.get("rubric", "")
        plag_enabled = batch.get("plagiarismEnabled", True)
        
        # Load staging submissions
        sub_docs = db.collection("submissions").where("batchJobId", "==", batch_id).stream()
        submissions = []
        for doc in sub_docs:
            submissions.append(doc.to_dict() or {})
            
        reports_aggregated = []
        processed_count = 0
        
        # Temporary directories for generating local PDF and Excel files
        with tempfile.TemporaryDirectory() as batch_dir:
            pdf_filepaths = []
            
            for index, sub in enumerate(submissions):
                sub_id = sub["id"]
                sub_text = sub["inputText"]
                sub_type = sub["type"]
                sub_file_name = sub["fileName"]
                student_name = sub.get("studentName", f"Student {index + 1}")
                
                logger.info(f"[Background Task] Processing index {index+1}/{len(submissions)} (Sub: {sub_id})")
                db.collection("submissions").document(sub_id).update({"status": "processing"})
                
                # Check warnings
                is_violated, violation_reason = await warning_service.scan_and_enforce(instructor_id, sub_id, sub_text)
                if is_violated:
                    logger.warning(f"[Background Task] Policy warning triggered in batch file: {sub_file_name}")
                    # Log failure record
                    db.collection("submissions").document(sub_id).update({
                        "status": "failed",
                        "violationMessage": violation_reason
                    })
                    processed_count += 1
                    batch_ref.update({"processedFiles": processed_count})
                    continue

                # Code execution if coding type
                if sub_type.lower() == "coding":
                    ext = os.path.splitext(sub_file_name)[1].lower()
                    lang = "python" if ext == '.py' else ("cpp" if ext in ['.cpp', '.h'] else "java")
                    exec_trace = await code_sandbox_service.execute_code(sub_text, lang)
                    sub_text += f"\n\n--- Standard Execution Diagnostics ---\nStdout:\n{exec_trace.get('stdout')}\nStderr:\n{exec_trace.get('stderr')}\n"

                # Run multi-agent pipeline
                report_data, spec_out, judge_out, senior_out = await feedback_pipeline.run_pipeline(
                    submission_text=sub_text,
                    assignment_prompt=prompt,
                    rubric=rubric
                )
                
                # Plagiarism scan
                plag_score = 0.0
                if plag_enabled:
                    plag_report = await plagiarism_service.check_plagiarism(sub_id, sub_text, batch_id)
                    plag_score = plag_report.get("similarityScore", 0.0)
                    # Record plagiarism report
                    plag_id = f"plag_{sub_id[:8]}"
                    db.collection("plagiarismReports").document(plag_id).set({
                        "id": plag_id,
                        "submissionId": sub_id,
                        "batchJobId": batch_id,
                        "similarityScore": plag_score,
                        "matches": plag_report.get("matches", []),
                        "createdAt": datetime.utcnow().isoformat()
                    })

                # Compile PDF Report
                rep_id = f"rep_{sub_id[:8]}"
                pdf_filename = f"{student_name.replace(' ', '_')}_{sub_id}_report.pdf"
                local_pdf_path = os.path.join(batch_dir, pdf_filename)
                
                await report_service.generate_student_pdf(
                    report_data=report_data,
                    student_name=student_name,
                    assignment_type=sub_type,
                    output_path=local_pdf_path
                )
                pdf_filepaths.append(local_pdf_path)
                
                # Upload PDF to Storage
                pdf_blob_name = f"reports/{instructor_id}/batch_{batch_id}/{pdf_filename}"
                pdf_blob = bucket.blob(pdf_blob_name)
                pdf_blob.upload_from_filename(local_pdf_path)
                student_pdf_url = pdf_blob.generate_signed_url()
                
                # Update Submission
                db.collection("submissions").document(sub_id).update({
                    "status": "completed",
                    "feedbackReportId": rep_id
                })
                
                # Save Feedback Report to db
                db.collection("feedbackReports").document(rep_id).set({
                    "id": rep_id,
                    "submissionId": sub_id,
                    "batchJobId": batch_id,
                    "studentName": student_name,
                    "overallScore": report_data.get("overallScore", 0),
                    "status": report_data.get("status", "pass"),
                    "strengths": report_data.get("strengths", []),
                    "weaknesses": report_data.get("weaknesses", []),
                    "suggestions": report_data.get("suggestions", []),
                    "rubricScores": report_data.get("rubricScores", []),
                    "specialistOutput": spec_out,
                    "judgeOutput": judge_out,
                    "seniorOutput": senior_out,
                    "pdfUrl": student_pdf_url,
                    "createdAt": datetime.utcnow().isoformat()
                })
                
                # Add to excel records list
                reports_aggregated.append({
                    "studentName": student_name,
                    "fileName": sub_file_name,
                    "overallScore": report_data.get("overallScore", 0),
                    "status": report_data.get("status", "pass"),
                    "strengths": report_data.get("strengths", []),
                    "weaknesses": report_data.get("weaknesses", []),
                    "suggestions": report_data.get("suggestions", []),
                    "plagiarismScore": plag_score,
                    "pdfUrl": student_pdf_url
                })
                
                processed_count += 1
                batch_ref.update({"processedFiles": processed_count})

            # --- BATCH AGGREGATIONS EXPORTS ---
            if reports_aggregated:
                # Compile Excel Worksheet
                excel_filename = "batch_grades_sheet.xlsx"
                local_excel_path = os.path.join(batch_dir, excel_filename)
                
                excel_final_path = await report_service.generate_batch_excel(
                    batch_data=reports_aggregated,
                    output_path=local_excel_path
                )
                
                # Detect actual export format (Excel vs CSV fallback)
                is_excel = excel_final_path.endswith('.xlsx')
                excel_blob_name = f"reports/{instructor_id}/batch_{batch_id}/batch_grades_sheet." + ("xlsx" if is_excel else "csv")
                
                excel_blob = bucket.blob(excel_blob_name)
                excel_blob.upload_from_filename(excel_final_path)
                export_excel_url = excel_blob.generate_signed_url()
                
                # Compile ZIP Archive containing Excel + All individual student PDFs
                zip_filename = f"batch_{batch_id}_all_reports.zip"
                local_zip_path = os.path.join(batch_dir, zip_filename)
                
                with zipfile.ZipFile(local_zip_path, 'w') as zip_file:
                    # Add grade sheet
                    zip_file.write(excel_final_path, arcname=os.path.basename(excel_final_path))
                    # Add PDFs
                    for pdf_path in pdf_filepaths:
                        zip_file.write(pdf_path, arcname=os.path.basename(pdf_path))
                        
                # Upload ZIP to Storage
                zip_blob_name = f"reports/{instructor_id}/batch_{batch_id}/{zip_filename}"
                zip_blob = bucket.blob(zip_blob_name)
                zip_blob.upload_from_filename(local_zip_path)
                export_zip_url = zip_blob.generate_signed_url()
                
                # Finalize Batch Document
                batch_ref.update({
                    "status": "completed",
                    "exportExcelUrl": export_excel_url,
                    "exportZipUrl": export_zip_url,
                    "processedFiles": len(submissions)
                })
                logger.info(f"[Background Task] Batch {batch_id} fully compiled. Excel and ZIP aggregated successfully.")
            else:
                batch_ref.update({"status": "failed"})
                logger.warning(f"[Background Task] Batch {batch_id} marked as failed due to zero evaluated elements.")
                
    except Exception as e:
        logger.error(f"[Background Task] Batch grading encountered a fatal error: {e}")
        try:
            db.collection("batchJobs").document(batch_id).update({"status": "failed"})
        except Exception:
            pass

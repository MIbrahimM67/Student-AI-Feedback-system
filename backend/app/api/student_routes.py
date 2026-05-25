import os
import tempfile
import uuid
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from typing import Optional, Dict, Any
from backend.app.firebase import db, bucket
from backend.app.utils.security import get_current_user, require_student
from backend.app.services.ocr_service import ocr_service
from backend.app.services.code_sandbox_service import code_sandbox_service
from backend.app.services.warning_service import warning_service
from backend.app.services.feedback_pipeline import feedback_pipeline
from backend.app.services.report_service import report_service

router = APIRouter(prefix="/api/student", tags=["Student Console"])
logger = logging.getLogger("student_routes")

@router.post("/submissions")
async def create_submission(
    type: str = Form(...), # 'text' | 'handwritten' | 'coding' | 'custom'
    prompt: str = Form(...),
    rubric: Optional[str] = Form(""),
    inputText: Optional[str] = Form(""),
    file: Optional[UploadFile] = File(None),
    user: Dict[str, Any] = Depends(require_student)
):
    """
    Submits a single assignment for instant AI evaluation.
    Performs OCR (if scan), compiles sandbox outputs (if code), checks moderation policies,
    runs the Specialist-Judge-Senior pipeline, renders ReportLab PDF, and returns grades.
    """
    uid = user["uid"]
    submission_id = f"sub_{str(uuid.uuid4())[:8]}"
    
    # 1. Enforce student single file size limit (1MB = 1048576 bytes)
    file_url = ""
    file_name = "pasted_text.txt"
    extracted_text = inputText or ""
    
    if file:
        file_name = file.filename
        content = await file.read()
        file_size = len(content)
        
        if file_size > 1048576:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Student uploads are limited to a maximum file size of 1MB."
            )
            
        # Write file temporarily to execute processors
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_name)[1]) as temp_file:
            temp_file.write(content)
            temp_file_path = temp_file.name

        try:
            # Upload original file to Firebase Storage
            blob_name = f"submissions/{uid}/{submission_id}_{file_name}"
            blob = bucket.blob(blob_name)
            
            # Reset pointer and upload
            blob.upload_from_filename(temp_file_path)
            file_url = blob.generate_signed_url()
            
            # 2. Extract text if PDF/image or run OCR if handwritten
            if type.lower() == "handwritten":
                extracted_text = await ocr_service.extract_text(temp_file_path, file_name)
            elif type.lower() == "coding":
                with open(temp_file_path, "r", encoding="utf-8", errors="ignore") as f:
                    extracted_text = f.read()
            else: # general document
                if file_name.lower().endswith('.pdf'):
                    # Call pyPDF fallback extraction
                    extracted_text = await ocr_service.extract_text(temp_file_path, file_name)
                else:
                    with open(temp_file_path, "r", encoding="utf-8", errors="ignore") as f:
                        extracted_text = f.read()
                        
        finally:
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
                
    if not extracted_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No readable text or code found. Please provide an input text or upload a valid file."
        )

    # Enforce student text limit (5000 chars)
    if len(extracted_text) > 5000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Assignment text length exceeds the free student tier limit of 5000 characters."
        )

    # 3. Policy Warning Scan
    is_violated, violation_reason = await warning_service.scan_and_enforce(uid, submission_id, extracted_text)
    if is_violated:
        # Save submission with failed state due to violation
        submission_data = {
            "id": submission_id,
            "userId": uid,
            "type": type,
            "mode": "single",
            "inputText": extracted_text,
            "fileUrl": file_url,
            "fileName": file_name,
            "prompt": prompt,
            "rubric": rubric,
            "status": "failed",
            "violationMessage": violation_reason,
            "createdAt": datetime.utcnow().isoformat()
        }
        db.collection("submissions").document(submission_id).set(submission_data)
        
        return {
            "status": "flagged",
            "detail": "Academic honesty warning triggered. Submission has been locked for review.",
            "reason": violation_reason
        }

    # 4. Coding Sandbox compilation execution (if coding)
    sandbox_logs = ""
    if type.lower() == "coding":
        # Extract programming language from file extension
        ext = os.path.splitext(file_name)[1].lower()
        lang = "python"
        if ext in ['.cpp', '.cc', '.h']:
            lang = "cpp"
        elif ext == '.java':
            lang = "java"
            
        exec_trace = await code_sandbox_service.execute_code(extracted_text, lang)
        stdout = exec_trace.get("stdout", "")
        stderr = exec_trace.get("stderr", "")
        
        # Format tracing output for the AI grader
        sandbox_logs = f"\n--- Sandboxed Compilation & Run Tracing ---\nLanguage: {lang.upper()}\nExit Code: {exec_trace.get('exitCode')}\nDuration: {exec_trace.get('durationMs')}ms\nStandard Output:\n{stdout}\nStandard Error/Lints:\n{stderr}\n"
        # Append trace to evaluation text
        extracted_text += sandbox_logs

    # 5. Run Specialist-Judge-Senior AI Agent Pipeline
    final_report, spec_out, judge_out, senior_out = await feedback_pipeline.run_pipeline(
        submission_text=extracted_text,
        assignment_prompt=prompt,
        rubric=rubric
    )
    
    report_id = f"rep_{submission_id[:8]}"
    
    # 6. Generate PDF Report Sheet
    pdf_url = ""
    with tempfile.TemporaryDirectory() as report_dir:
        pdf_filename = f"{submission_id}_feedback.pdf"
        temp_pdf_path = os.path.join(report_dir, pdf_filename)
        
        generated_report_path = await report_service.generate_student_pdf(
            report_data=final_report,
            student_name=user.get("displayName", "Student"),
            assignment_type=type,
            output_path=temp_pdf_path
        )
        
        # Upload report to Storage
        report_blob_name = f"reports/{uid}/{pdf_filename}"
        report_blob = bucket.blob(report_blob_name)
        report_blob.upload_from_filename(generated_report_path)
        pdf_url = report_blob.generate_signed_url()

    # 7. Write documents into Firestore collections
    submission_data = {
        "id": submission_id,
        "userId": uid,
        "type": type,
        "mode": "single",
        "inputText": inputText or extracted_text,
        "fileUrl": file_url,
        "fileName": file_name,
        "prompt": prompt,
        "rubric": rubric,
        "status": "completed",
        "feedbackReportId": report_id,
        "createdAt": datetime.utcnow().isoformat()
    }
    db.collection("submissions").document(submission_id).set(submission_data)
    
    feedback_report = {
        "id": report_id,
        "submissionId": submission_id,
        "batchJobId": None,
        "studentName": user.get("displayName", "Student"),
        "overallScore": final_report.get("overallScore", 0),
        "status": final_report.get("status", "pass"),
        "strengths": final_report.get("strengths", []),
        "weaknesses": final_report.get("weaknesses", []),
        "suggestions": final_report.get("suggestions", []),
        "rubricScores": final_report.get("rubricScores", []),
        "specialistOutput": spec_out,
        "judgeOutput": judge_out,
        "seniorOutput": senior_out,
        "pdfUrl": pdf_url,
        "createdAt": datetime.utcnow().isoformat()
    }
    db.collection("feedbackReports").document(report_id).set(feedback_report)
    
    return {
        "submissionId": submission_id,
        "reportId": report_id,
        "evaluation": final_report,
        "pdfUrl": pdf_url
    }

@router.get("/submissions/{id}")
async def get_submission(id: str, user: Dict[str, Any] = Depends(require_student)):
    """
    Retrieves core submission records.
    """
    sub_snap = db.collection("submissions").document(id).get()
    if not sub_snap.exists:
        raise HTTPException(status_code=404, detail="Submission record not found.")
        
    data = sub_snap.to_dict() or {}
    if data.get("userId") != user["uid"]:
        raise HTTPException(status_code=403, detail="Unprivileged access forbidden.")
    return data

@router.get("/submissions/{id}/feedback")
async def get_feedback(id: str, user: Dict[str, Any] = Depends(require_student)):
    """
    Retrieves the parsed feedback report details.
    """
    submission = await get_submission(id, user)
    report_id = submission.get("feedbackReportId")
    
    if not report_id:
        raise HTTPException(status_code=400, detail="This submission has no associated evaluation completed.")
        
    rep_snap = db.collection("feedbackReports").document(report_id).get()
    if not rep_snap.exists:
        raise HTTPException(status_code=404, detail="Feedback report document not found.")
        
    return rep_snap.to_dict()

@router.get("/submissions/{id}/download-pdf")
async def download_pdf(id: str, user: Dict[str, Any] = Depends(require_student)):
    """
    Returns the student report PDF URL link.
    """
    submission = await get_submission(id, user)
    report_id = submission.get("feedbackReportId")
    
    if not report_id:
        raise HTTPException(status_code=400, detail="Submission is not evaluated.")
        
    rep_snap = db.collection("feedbackReports").document(report_id).get()
    if not rep_snap.exists:
        raise HTTPException(status_code=404, detail="Report not compiled.")
        
    report_data = rep_snap.to_dict() or {}
    pdf_url = report_data.get("pdfUrl")
    
    return {"pdfUrl": pdf_url}

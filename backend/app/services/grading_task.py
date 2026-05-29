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
from app.services.llm_provider import build_llm_from_env
from app.services.ocr_service import ocr_service
from app.services.warning_service import warning_service
from app.utils.prompt_templates import utility_title_generator_user
from app.grading.pipeline import grade_submission as route_and_grade


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

    NOTE: The asyncpg pool lifecycle is managed by _run_async in celery_app.py,
    which creates a fresh pool for every Celery task execution.
    """
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
    detected_lang = None
    tmp_zip_path = None
    files_to_cleanup = []

    if sub["file_url"] and not extracted_text.strip():
        try:
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(sub["file_url"])
                resp.raise_for_status()

            ext = os.path.splitext(sub["file_name"] or ".pdf")[1].lower()
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name
            files_to_cleanup.append(tmp_path)

            if ext == ".zip":
                tmp_zip_path = tmp_path
                import zipfile
                extracted_text = ""
                lang_counts = {"cpp": 0, "python": 0, "java": 0, "web": 0}
                with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                    for zip_info in zip_ref.infolist():
                        if zip_info.is_dir(): continue
                        file_ext = os.path.splitext(zip_info.filename)[1].lower()
                        
                        if file_ext in [".cpp", ".cc", ".h", ".c"]: lang_counts["cpp"] += 1
                        elif file_ext == ".py": lang_counts["python"] += 1
                        elif file_ext == ".java": lang_counts["java"] += 1
                        elif file_ext in [".html", ".js", ".css"]: lang_counts["web"] += 1

                        if file_ext in [".py", ".cpp", ".cc", ".h", ".c", ".java", ".js", ".html", ".css", ".txt"]:
                            with zip_ref.open(zip_info) as f:
                                try:
                                    content = f.read().decode('utf-8')
                                    extracted_text += f"\n=== {zip_info.filename} ===\n{content}\n"
                                except UnicodeDecodeError:
                                    pass
                if sum(lang_counts.values()) > 0:
                    detected_lang = max(lang_counts, key=lang_counts.get)
            else:
                extracted_text = await ocr_service.extract_text(tmp_path, sub["file_name"] or "file")
        except Exception as e:
            logger.error("Text extraction failed for submission %s: %s", submission_id, e)
            await _mark_failed(org_id, submission_id, batch_id)
            return

    if not extracted_text.strip():
        await _mark_failed(org_id, submission_id, batch_id)
        return

    # ---- Generate Title (if text submission) --------------------------------
    if not sub["file_url"] and sub["question_text"] and not sub["file_name"]:
        try:
            llm = build_llm_from_env()
            from app.services.llm_provider import ChatMessage
            resp = await llm.chat(
                messages=[ChatMessage(role="user", content=utility_title_generator_user(sub["question_text"]))],
                model=settings.GRADIENT_MODEL_UTILITY,
                temperature=0.3,
                max_tokens=10,
            )
            generated_title = resp.text.strip().strip('"').strip("'")
            if generated_title:
                async with get_conn(org_id) as conn:
                    await conn.execute("UPDATE submissions SET file_name = $1 WHERE id = $2", generated_title, submission_id)
        except Exception as e:
            logger.warning("Failed to generate title for submission %s: %s", submission_id, e)

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
            from app.utils.prompt_templates import utility_test_case_generator_user
            from app.services.llm_provider import ChatMessage
            
            if detected_lang:
                lang = detected_lang
            else:
                ext = os.path.splitext(sub["file_name"] or ".py")[1].lower()
                lang = "python" if ext == ".py" else ("cpp" if ext in (".cpp", ".cc") else "java")
            
            if lang == "web":
                code_execution_result = "Status: SKIPPED\nWeb assignment detected (HTML/CSS/JS). Relying on AI static analysis instead of terminal sandbox."
            else:
                # 1. Generate autonomous test cases via LLM
                llm = build_llm_from_env()
            is_batch = sub["mode"] == "batch"
            test_gen_prompt = utility_test_case_generator_user(extracted_text, sub.get("stdin_text", ""), is_batch)
            
            resp = await llm.chat(
                messages=[ChatMessage(role="user", content=test_gen_prompt)],
                model=settings.GRADIENT_MODEL_UTILITY,
                temperature=0.4,
                max_tokens=800,
            )
            
            # Safely parse JSON from LLM response
            json_str = resp.text.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:-3]
            elif json_str.startswith("```"):
                json_str = json_str[3:-3]
                
            test_cases = [{"name": "Default Test", "input": sub.get("stdin_text", "")}]
            try:
                parsed = json.loads(json_str)
                if "test_cases" in parsed and isinstance(parsed["test_cases"], list) and len(parsed["test_cases"]) > 0:
                    test_cases = parsed["test_cases"]
            except Exception as e:
                logger.warning("Failed to parse test cases from LLM: %s", e)
            
            # 2. Execute test cases sequentially
            if code_execution_result is None:  # Ensure we didn't skip it (like web)
                execution_results = []
                for tc in test_cases:
                    tc_name = tc.get("name", "Test Case")
                    tc_input = tc.get("input", "")
                    result = await code_sandbox_service.execute_code(extracted_text, lang, stdin_text=tc_input, zip_path=tmp_zip_path)
                    
                    # Apply user requested formatting: Passed/Failed with capped output
                    if result.get("exitCode") == 0:
                        out_str = f"=== Test Case: {tc_name} ===\nStatus: PASSED\nOutput:\n{result.get('stdout', '').strip()[:500]}"
                    else:
                        out_str = f"=== Test Case: {tc_name} ===\nStatus: FAILED\nErrors/Reasons:\n{result.get('stderr', '').strip()[:500]}"
                    
                    execution_results.append(out_str)
                    
                code_execution_result = "\n\n".join(execution_results)
            
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

    # ---- Run pipeline -------------------------------------------------------
    try:
        # Get raw rubric text from criteria list or fallback
        raw_rubric = "\n".join([f"{c['name']}: {c['description']}" for c in rubric_criteria]) if rubric_criteria else sub.get("rubric_text", "Evaluate comprehensively.")
        
        # We need physical paths for the new ingestion pipeline (PyMuPDF needs files)
        # We already downloaded the submission to tmp_path if it was a file, else we need a temp text file.
        sub_path_for_pipeline = None
        ref_path_for_pipeline = None
        pipeline_cleanup = []

        if "tmp_path" in locals() and tmp_path and os.path.exists(tmp_path):
            sub_path_for_pipeline = tmp_path
        else:
            # It's a text submission
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt", encoding='utf-8') as f:
                f.write(extracted_text)
                sub_path_for_pipeline = f.name
                pipeline_cleanup.append(f.name)

        if sub.get("reference_file_url"):
            # Download reference file for the pipeline
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(sub["reference_file_url"])
                resp.raise_for_status()

            ext = os.path.splitext(sub.get("reference_file_name") or ".pdf")[1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(resp.content)
                ref_path_for_pipeline = tmp.name
                pipeline_cleanup.append(ref_path_for_pipeline)
        else:
             # Create empty dummy text file if no reference provided
             with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix=".txt", encoding='utf-8') as f:
                f.write("No reference provided.")
                ref_path_for_pipeline = f.name
                pipeline_cleanup.append(f.name)
        
        report = await route_and_grade(
            submission_path=sub_path_for_pipeline,
            reference_path=ref_path_for_pipeline,
            raw_rubric=raw_rubric,
            org_id=org_id,
            subject_id=subject_id or str(uuid.uuid4())
        )
    except Exception as e:
        logger.error("Pipeline failed for submission %s: %s", submission_id, e)
        await _mark_failed(org_id, submission_id, batch_id)
        return
    finally:
        for tmp_file in files_to_cleanup:
            if os.path.exists(tmp_file):
                os.remove(tmp_file)
        if "pipeline_cleanup" in locals():
            for tmp_file in pipeline_cleanup:
                 if os.path.exists(tmp_file):
                    os.remove(tmp_file)
        await redis.aclose()

    # ---- Persist feedback_report --------------------------------------------
    now = datetime.now(timezone.utc)
    
    # GradingResult doesn't have a model_dump(), so we serialize to dict manually
    report_dict = {
        "score": report.score,
        "max_score": report.max_score,
        "per_criterion": report.per_criterion,
        "feedback": report.feedback,
        "tier_used": report.tier_used.value,
        "reference_sections_used": report.reference_sections_used,
        "latency_ms": report.latency_ms,
        "est_cost_usd": report.est_cost_usd,
        "code_execution_result": code_execution_result  # Keep this for the UI
    }
    
    # The new pipeline doesn't output confidence (which was mostly fake anyway) or status directly.
    # We map score to a binary 'needs_review' based on threshold or just default to published.
    avg_confidence = 0.9 
    ai_status = "published" if not batch_id else "needs_review"
    needs_review = ai_status == "needs_review"

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
            report.score, report.max_score, ai_status,
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

        # Auto-publish student single submissions — they don't need instructor review.
        # Batch submissions stay at 'graded' for the instructor review workflow.
        if not batch_id:
            await conn.execute(
                """
                UPDATE submissions SET status = 'published' WHERE id = $1
                """,
                submission_id,
            )
            await conn.execute(
                """
                UPDATE feedback_reports SET
                  final_overall_score = ai_overall_score,
                  final_max_score     = ai_max_score,
                  final_status        = ai_status,
                  final_payload       = ai_payload,
                  published_at        = $2
                WHERE submission_id = $1
                """,
                submission_id, now,
            )
        else:
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

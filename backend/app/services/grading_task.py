"""
GradeWise v3 — grading task helpers.

Called by Celery `grade_submission` task.
Orchestrates: load submission → extract text → scan → pipeline → persist.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone

from app.config import settings
from app.services.demo_limits import code_execution_available
from app.db.postgres import get_conn
from app.db.vectors import internal_similarity_search, upsert_submission_chunks
from app.services.llm_provider import build_llm_from_env
from app.services.ocr_service import ocr_service
from app.services.retrieval_service import retrieve_and_rerank
from app.services.entitlements import assignment_owner_is_verified
from app.services.warning_service import warning_service
from app.utils.prompt_templates import utility_title_generator_user
from app.grading.pipeline import grade_submission as route_and_grade



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
    # Also cleans up files on early failure, cancellation and provider errors.
    with tempfile.TemporaryDirectory(prefix="gradewise-job-") as work_dir:
        await _run_grade_submission(submission_id, org_id, work_dir)


async def _run_grade_submission(submission_id: str, org_id: str, work_dir: str) -> None:
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

    # ---- Load submission -----------------------------------------------------
    async with get_conn(org_id) as conn:
        sub = await conn.fetchrow(
            "SELECT * FROM submissions WHERE id = $1", submission_id
        )
        if not sub:
            logger.error("Submission %s not found", submission_id)
            return

        if sub["type"] == "coding" and not code_execution_available():
            await conn.execute("UPDATE submissions SET status='failed', progress_message='Code grading is paused.' WHERE id=$1", submission_id)
            return

        await conn.execute(
            "UPDATE submissions SET status = 'processing' WHERE id = $1", submission_id
        )

        # Load assignment + rubric
        assignment = None
        questions = []
        rubric_criteria = []
        similarity_entitled = False
        if sub["assignment_id"]:
            assignment = await conn.fetchrow(
                "SELECT * FROM assignments WHERE id = $1", sub["assignment_id"]
            )
            similarity_entitled = await assignment_owner_is_verified(conn, sub["assignment_id"])
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
    assignment_settings = dict(assignment) if assignment else {}
    if assignment_settings and not similarity_entitled:
        # Disable similarity if the assignment owner no longer has faculty approval.
        assignment_settings["internal_similarity_enabled"] = False
        assignment_settings["internet_plagiarism_enabled"] = False

    async def progress(stage: str, percent: int, message: str) -> None:
        await _set_progress(org_id, submission_id, stage, percent, message)

    await progress("queued", 5, f"{student_name}'s submission is queued for AI grading.")

    # ---- Extract text -------------------------------------------------------
    extracted_text = sub["input_text"] or ""
    detected_lang = None
    tmp_zip_path = None
    files_to_cleanup = []

    if sub["file_url"] and not extracted_text.strip():
        try:
            await progress(
                "extracting",
                15,
                "Extracting text, diagrams, charts, tables, and visual evidence from the file.",
            )
            from app.services.file_storage import materialize
            ext = os.path.splitext(sub["file_name"] or ".pdf")[1].lower()
            async with materialize(sub["file_url"], sub["file_name"] or "file.pdf", org_id) as source_path:
                # Keep the working copy alive until all extraction/grading paths finish.
                import shutil
                with tempfile.NamedTemporaryFile(dir=work_dir, delete=False, suffix=ext) as temp:
                    tmp_path = temp.name
                files_to_cleanup.append(tmp_path)
                shutil.copyfile(source_path, tmp_path)

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
                extracted_text = await ocr_service.extract_text(
                    tmp_path,
                    sub["file_name"] or "file",
                    skip_vision=(
                        sub.get("type") == "coding"
                        or ext in {".py", ".java", ".cpp", ".c", ".js", ".ts", ".txt"}
                    ),
                )
        except Exception as e:
            logger.error("Text extraction failed for submission %s: %s", submission_id, e)
            await _mark_failed(org_id, submission_id, batch_id)
            return

    if not extracted_text.strip() or (settings.DOCUMENT_DEMO and len(extracted_text) > settings.DEMO_MAX_TEXT_CHARS):
        await _mark_failed(org_id, submission_id, batch_id)
        return

    await progress("evidence_ready", 28, "Submission evidence is ready for policy and grading checks.")

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
            await progress("reference_extracting", 32, "Extracting reference material for comparison.")
            from app.services.file_storage import materialize
            async with materialize(sub["reference_file_url"], sub.get("reference_file_name") or "reference.pdf", org_id) as ref_tmp_path:
                reference_text = await ocr_service.extract_text(ref_tmp_path, sub.get("reference_file_name") or "reference.pdf")
                if not reference_text.strip() or (settings.DOCUMENT_DEMO and len(reference_text) > settings.DEMO_MAX_TEXT_CHARS):
                    raise ValueError("Reference is empty or exceeds the demo text limit")
        except Exception as e:
            logger.warning("Reference text extraction failed for submission %s: %s", submission_id, e)
            await _mark_failed(org_id, submission_id, batch_id)
            for path in files_to_cleanup:
                if os.path.exists(path):
                    os.remove(path)
            return

    # ---- Policy scan --------------------------------------------------------
    await progress("policy_scan", 36, "Checking the submission for blocked prompt-injection or policy issues.")
    is_violated, reason = await warning_service.scan_and_enforce(
        org_id=org_id,
        # Instructor uploads have no student account to warn or block.
        user_id=str(sub["user_id"]) if sub["user_id"] else None,
        submission_id=submission_id,
        text=extracted_text,
    )
    if is_violated:
        await _mark_failed(
            org_id,
            submission_id,
            batch_id,
            f"Grading stopped by the policy scan ({reason}). No report was generated.",
        )
        for path in files_to_cleanup:
            if os.path.exists(path):
                os.remove(path)
        return

    async with get_conn(org_id) as conn:
        await conn.execute("UPDATE submissions SET input_text=$2 WHERE id=$1", submission_id, extracted_text)

    integrity_report = None
    if assignment_settings and not settings.DOCUMENT_DEMO and (
        assignment_settings.get("internal_similarity_enabled", True)
        or assignment_settings.get("internet_plagiarism_enabled", False)
    ):
        await progress("integrity_checks", 39, "Checking internal similarity and plagiarism settings.")
        integrity_report = await _run_integrity_checks(
            llm=llm,
            org_id=org_id,
            submission_id=submission_id,
            batch_id=batch_id,
            assignment_id=str(sub["assignment_id"]) if sub["assignment_id"] else None,
            subject_id=subject_id,
            submission_text=extracted_text,
            internal_enabled=bool(assignment_settings.get("internal_similarity_enabled", True)),
            internet_enabled=bool(assignment_settings.get("internet_plagiarism_enabled", False)),
        )

    # ---- Code sandbox -------------------------------------------------------
    code_execution_result = None
    if sub["type"] == "coding" and code_execution_available():
        try:
            await progress("code_checks", 40, "Generating and running code checks before grading.")
            from app.services.code_sandbox_service import code_sandbox_service
            from app.utils.prompt_templates import utility_test_case_generator_user
            from app.services.llm_provider import ChatMessage
            
            if detected_lang:
                lang = detected_lang
            else:
                ext = os.path.splitext(sub["file_name"] or ".py")[1].lower()
                lang = "java" if ext == ".java" else ("cpp" if ext in (".cpp", ".cc", ".cxx") else "python")
            
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
                    test_cases = [tc for tc in test_cases if isinstance(tc, dict)][:5]
                    if not test_cases:
                        raise RuntimeError("No usable code checks were generated")
                    inputs = [str(tc.get("input", ""))[:8000] for tc in test_cases]
                    results = await code_sandbox_service.execute_tests(extracted_text, lang, inputs, zip_path=tmp_zip_path)
                    for tc, result in zip(test_cases, results):
                        tc_name = tc.get("name", "Test Case")
                        tc_input = tc.get("input", "")
                    
                        # Apply user requested formatting: Passed/Failed with capped output
                        if result.get("exitCode") == 0:
                            out_str = f"=== Test Case: {tc_name} ===\nStatus: EXECUTED (exit code 0; correctness judged against the rubric)\nInput:\n{str(tc_input)[:8000]}\nOutput:\n{result.get('stdout', '').strip()[:4000]}\nStderr:\n{result.get('stderr', '').strip()[:1000]}"
                        else:
                            out_str = f"=== Test Case: {tc_name} ===\nStatus: FAILED (exit code {result.get('exitCode')})\nInput:\n{str(tc_input)[:8000]}\nOutput:\n{result.get('stdout', '').strip()[:4000]}\nErrors/Reasons:\n{result.get('stderr', '').strip()[:1000]}"
                    
                        execution_results.append(out_str)
                    
                    code_execution_result = "\n\n".join(execution_results)
            
        except Exception as e:
            logger.warning("Code sandbox failed: %s", e)
            await progress("failed", 40, "Real code execution failed. No simulated evidence or grade was generated.")
            await _mark_failed(org_id, submission_id, batch_id)
            return

    # ---- Build pipeline inputs ----------------------------------------------
    await progress("context_building", 44, "Building the grading context from the assignment, rubric, and evidence.")
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
        raw_rubric = (
            "\n".join([f"{c['name']} ({c.get('max_score', 100)} pts): {c['description']}" for c in rubric_criteria])
            if rubric_criteria
            else (sub.get("rubric_text") or None)
        ) or "Evaluate the overall quality, correctness, and completeness of the submission."

        assignment_dict = dict(assignment) if assignment else {}
        if assignment_dict:
            raw_rubric = (
                f"Total/highest marks: {assignment_dict.get('total_marks', 100)}.\n"
                f"Lowest allowed marks: {assignment_dict.get('minimum_marks', 0)}.\n"
                f"{raw_rubric}"
            )
        if subject_id and assignment_dict.get("use_subject_kb", True):
            course_weight = int(assignment_dict.get("course_material_weight", 60))
            ai_weight = int(assignment_dict.get("ai_expertise_weight") or (100 - course_weight))
            await progress(
                "retrieving_reference",
                48,
                f"Retrieving subject knowledge base context ({course_weight}% course material / {ai_weight}% AI expertise).",
            )
            kb_context = await _retrieve_subject_kb_context(
                llm=llm,
                org_id=org_id,
                subject_id=subject_id,
                assignment_prompt=questions[0]["text"] if questions else "",
                raw_rubric=raw_rubric,
                submission_text=extracted_text,
                course_weight=course_weight,
                ai_weight=ai_weight,
            )
            if kb_context:
                reference_text = (
                    f"{reference_text}\n\n{kb_context}"
                    if reference_text
                    else kb_context
                )
                raw_rubric = (
                    f"{raw_rubric}\n\n"
                    f"Grounding policy: rubric criteria are mandatory. Use retrieved course material "
                    f"as {course_weight}% of the domain grounding and AI expertise as {ai_weight}%. "
                    "If retrieved chunks are irrelevant or missing, do not invent course facts."
                )
        
        # We need physical paths for the new ingestion pipeline (PyMuPDF needs files)
        # We already downloaded the submission to tmp_path if it was a file, else we need a temp text file.
        sub_path_for_pipeline = None
        ref_path_for_pipeline = None
        pipeline_cleanup = []

        # All extracted evidence enters the document grader as UTF-8 text.
        # Source files retain their original extension for execution, while
        # ingestion receives a supported .txt file with identical source text.
        with tempfile.NamedTemporaryFile(dir=work_dir, mode='w', delete=False, suffix=".txt", encoding='utf-8') as f:
            f.write(extracted_text)
            sub_path_for_pipeline = f.name
            pipeline_cleanup.append(f.name)

        if reference_text:
            with tempfile.NamedTemporaryFile(dir=work_dir, mode='w', delete=False, suffix=".txt", encoding='utf-8') as f:
                f.write(reference_text)
                ref_path_for_pipeline = f.name
                pipeline_cleanup.append(ref_path_for_pipeline)
        else:
             # Create empty dummy text file if no reference provided
             with tempfile.NamedTemporaryFile(dir=work_dir, mode='w', delete=False, suffix=".txt", encoding='utf-8') as f:
                f.write("No reference provided.")
                ref_path_for_pipeline = f.name
                pipeline_cleanup.append(f.name)
        
        report = await route_and_grade(
            submission_path=sub_path_for_pipeline,
            reference_path=ref_path_for_pipeline,
            raw_rubric=raw_rubric,
            org_id=org_id,
            subject_id=subject_id or str(uuid.uuid4()),
            progress_callback=progress,
            code_execution_evidence=code_execution_result,
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

    # ---- Persist feedback_report --------------------------------------------
    await progress("finalizing", 96, "Saving the final feedback report for instructor review.")
    now = datetime.now(timezone.utc)
    assignment_limits = dict(assignment) if assignment else {}
    minimum_marks = float(assignment_limits.get("minimum_marks") or 0)
    total_marks = float(assignment_limits.get("total_marks") or report.max_score or 100)
    if total_marks > 0:
        report.score = round(min(max(float(report.score), minimum_marks), total_marks), 2)
        report.max_score = total_marks
    
    # GradingResult doesn't have a model_dump(), so we serialize to dict manually
    report_dict = {
        "summary": report.student_feedback or report.feedback,
        "finalComments": report.score_rationale,
        "extractedText": extracted_text,
        "score": report.score,
        "max_score": report.max_score,
        "per_criterion": report.per_criterion,
        "feedback": report.feedback,
        "instructor_brief": report.instructor_brief,
        "student_feedback": report.student_feedback,
        "verdict": report.verdict,
        "score_rationale": report.score_rationale,
        "strengths": report.strengths,
        "weaknesses": report.weaknesses,
        "suggestions": report.suggestions,
        "priority_actions": report.priority_actions,
        "criteria_notes": report.criteria_notes,
        "tier_used": report.tier_used.value,
        "reference_sections_used": report.reference_sections_used,
        "latency_ms": report.latency_ms,
        "est_cost_usd": report.est_cost_usd,
        "code_execution_result": code_execution_result,
        "sandbox_logs": code_execution_result,
        "integrity_report": integrity_report,
    }
    
    # This pipeline does not measure confidence. Do not invent a percentage.
    avg_confidence = None
    ai_status = "needs_review"
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

    await progress("completed", 100, "AI grading complete. Report is ready for review.")


async def _set_progress(
    org_id: str,
    submission_id: str,
    stage: str,
    percent: int,
    message: str,
) -> None:
    percent = max(0, min(100, int(percent)))
    try:
        async with get_conn(org_id) as conn:
            await conn.execute(
                """
                UPDATE submissions
                SET progress_stage = $2,
                    progress_percent = $3,
                    progress_message = $4,
                    progress_updated_at = now()
                WHERE id = $1
                """,
                submission_id,
                stage,
                percent,
                message,
            )
    except Exception as e:  # noqa: BLE001
        logger.warning("Could not update grading progress for %s: %s", submission_id, e)


async def _run_integrity_checks(
    *,
    llm,
    org_id: str,
    submission_id: str,
    batch_id: str | None,
    assignment_id: str | None,
    subject_id: str | None,
    submission_text: str,
    internal_enabled: bool,
    internet_enabled: bool,
) -> dict:
    matches: list[dict] = []
    internal_score = 0.0
    internet_score = 0.0

    if internal_enabled:
        internal_matches = await _run_internal_similarity_check(
            llm=llm,
            org_id=org_id,
            submission_id=submission_id,
            batch_id=batch_id,
            assignment_id=assignment_id,
            subject_id=subject_id,
            submission_text=submission_text,
        )
        matches.extend(internal_matches)
        internal_score = max((float(m.get("similarity", 0.0)) for m in internal_matches), default=0.0)

    if internet_enabled:
        internet_matches = await _run_internet_plagiarism_check(submission_text)
        matches.extend(internet_matches)
        internet_score = max((float(m.get("similarity", 0.0)) for m in internet_matches), default=0.0)

    similarity_score = round(max(internal_score, internet_score), 2)
    result = {
        "similarity_score": similarity_score,
        "internal_similarity_enabled": internal_enabled,
        "internet_plagiarism_enabled": internet_enabled,
        "matches": matches[:10],
    }

    async with get_conn(org_id) as conn:
        await conn.execute(
            """
            INSERT INTO plagiarism_reports
              (id, org_id, submission_id, batch_id, similarity_score, matches, created_at)
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            """,
            str(uuid.uuid4()),
            org_id,
            submission_id,
            batch_id,
            similarity_score,
            json.dumps(result["matches"]),
            datetime.now(timezone.utc),
        )

    return result


async def _run_internal_similarity_check(
    *,
    llm,
    org_id: str,
    submission_id: str,
    batch_id: str | None,
    assignment_id: str | None,
    subject_id: str | None,
    submission_text: str,
) -> list[dict]:
    chunks = _chunk_for_similarity(submission_text)
    if not chunks:
        return []

    embeddings = await llm.embed(texts=chunks, model=settings.GRADIENT_EMBED_MODEL)
    await upsert_submission_chunks(
        org_id=org_id,
        submission_id=submission_id,
        batch_id=batch_id,
        chunks=[
            {"chunk_index": idx, "text": text, "embedding": embeddings[idx]}
            for idx, text in enumerate(chunks)
        ],
    )

    best_by_submission: dict[str, dict] = {}
    for idx, embedding in enumerate(embeddings):
        rows = await internal_similarity_search(
            org_id=org_id,
            submission_id=submission_id,
            query_embedding=embedding,
            batch_id=batch_id,
            assignment_id=assignment_id,
            subject_id=subject_id,
            top_k=6,
        )
        for row in rows:
            score = float(row.get("score") or 0.0)
            if score < 0.78:
                continue
            other_id = str(row["submission_id"])
            score_percent = round(score * 100, 2)
            if other_id not in best_by_submission or score_percent > best_by_submission[other_id]["similarity"]:
                best_by_submission[other_id] = {
                    "type": "internal_similarity",
                    "sourceSubmissionId": other_id,
                    "sourceName": f"{row.get('student_name') or 'Unknown student'} ({row.get('file_name') or 'submission'})",
                    "matchedText": _overlap_snippet(chunks[idx], str(row.get("text") or "")),
                    "similarity": score_percent,
                    "scope": _match_scope(row, batch_id, assignment_id, subject_id),
                }

    return sorted(best_by_submission.values(), key=lambda item: item["similarity"], reverse=True)[:5]


async def _run_internet_plagiarism_check(submission_text: str) -> list[dict]:
    if settings.DIGITALOCEAN_WEB_SEARCH_AGENT_URL and settings.DIGITALOCEAN_WEB_SEARCH_AGENT_KEY:
        return await _run_digitalocean_web_plagiarism_agent(submission_text)

    if not settings.INTERNET_PLAGIARISM_SEARCH_URL or not settings.INTERNET_PLAGIARISM_SEARCH_KEY:
        return [{
            "type": "internet_plagiarism",
            "status": "not_configured",
            "sourceName": "Internet plagiarism search is disabled",
            "matchedText": (
                "Configure DIGITALOCEAN_WEB_SEARCH_AGENT_URL and DIGITALOCEAN_WEB_SEARCH_AGENT_KEY "
                "to enable DigitalOcean-powered web plagiarism search."
            ),
            "similarity": 0.0,
        }]

    import httpx

    passages = _select_search_passages(submission_text)
    matches: list[dict] = []
    headers = {
        "X-API-KEY": settings.INTERNET_PLAGIARISM_SEARCH_KEY,
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20.0) as client:
        for passage in passages:
            try:
                resp = await client.post(
                    settings.INTERNET_PLAGIARISM_SEARCH_URL,
                    headers=headers,
                    json={"q": f'"{passage[:220]}"', "num": 5},
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                logger.warning("Internet plagiarism search failed: %s", e)
                continue

            for item in data.get("organic", [])[:5]:
                haystack = " ".join([
                    str(item.get("title", "")),
                    str(item.get("snippet", "")),
                ])
                score = _lexical_similarity(passage, haystack)
                if score < 0.22:
                    continue
                matches.append({
                    "type": "internet_plagiarism",
                    "sourceUrl": item.get("link"),
                    "sourceName": item.get("title") or item.get("link") or "Web source",
                    "matchedText": item.get("snippet") or passage[:280],
                    "similarity": round(score * 100, 2),
                })

    deduped: dict[str, dict] = {}
    for match in matches:
        key = str(match.get("sourceUrl") or match.get("sourceName"))
        if key not in deduped or match["similarity"] > deduped[key]["similarity"]:
            deduped[key] = match
    return sorted(deduped.values(), key=lambda item: item["similarity"], reverse=True)[:5]


async def _run_digitalocean_web_plagiarism_agent(submission_text: str) -> list[dict]:
    import httpx

    passages = _select_search_passages(submission_text)
    if not passages:
        return []

    prompt = (
        "You are an internet plagiarism search agent. Search the public web for the provided "
        "student-submission passages. Return ONLY valid JSON in this shape:\n"
        '{"matches":[{"sourceUrl":"https://...","sourceName":"page title","matchedText":"snippet",'
        '"similarity":42.5}]}\n'
        "Use similarity as a 0-100 percentage. Include only sources that show meaningful textual overlap. "
        "Do not accuse plagiarism; report evidence for instructor review.\n\n"
        "Passages to search:\n"
        + "\n\n".join(f"{idx + 1}. {passage}" for idx, passage in enumerate(passages))
    )
    headers = {
        "Authorization": f"Bearer {settings.DIGITALOCEAN_WEB_SEARCH_AGENT_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "messages": [
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(
                settings.DIGITALOCEAN_WEB_SEARCH_AGENT_URL,
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.warning("DigitalOcean web plagiarism agent failed: %s", e)
        return [{
            "type": "internet_plagiarism",
            "status": "search_failed",
            "sourceName": "DigitalOcean web search agent",
            "matchedText": str(e),
            "similarity": 0.0,
        }]

    text = _agent_response_text(data)
    parsed = _extract_json_object(text) if text else data
    matches = parsed.get("matches", []) if isinstance(parsed, dict) else []
    normalised = []
    for match in matches:
        if not isinstance(match, dict):
            continue
        normalised.append({
            "type": "internet_plagiarism",
            "sourceUrl": match.get("sourceUrl") or match.get("url"),
            "sourceName": match.get("sourceName") or match.get("title") or "Web source",
            "matchedText": match.get("matchedText") or match.get("snippet") or "",
            "similarity": round(float(match.get("similarity") or 0.0), 2),
        })
    return sorted(normalised, key=lambda item: item["similarity"], reverse=True)[:5]


def _chunk_for_similarity(text: str, chunk_size: int = 1_600, overlap: int = 250) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if not cleaned:
        return []
    chunks = []
    start = 0
    while start < len(cleaned):
        part = cleaned[start:start + chunk_size].strip()
        if len(part) > 120:
            chunks.append(part)
        start += max(1, chunk_size - overlap)
    return chunks[:24]


def _select_search_passages(text: str) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text or "").strip())
    candidates = [
        sentence.strip()
        for sentence in sentences
        if 80 <= len(sentence.strip()) <= 260
    ]
    candidates.sort(key=lambda s: (len(set(re.findall(r"\w+", s.lower()))), len(s)), reverse=True)
    return candidates[:4]


def _agent_response_text(data: dict) -> str:
    try:
        return str(data["choices"][0]["message"]["content"])
    except Exception:
        pass
    for key in ("answer", "output", "response", "content", "text"):
        if key in data:
            return str(data[key])
    return json.dumps(data)


def _extract_json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text or ""):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text, index)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue
    return {}


def _lexical_similarity(text_a: str, text_b: str) -> float:
    words_a = re.findall(r"\w+", (text_a or "").lower())
    words_b = re.findall(r"\w+", (text_b or "").lower())
    if not words_a or not words_b:
        return 0.0
    vec_a = Counter(words_a)
    vec_b = Counter(words_b)
    common = set(vec_a) & set(vec_b)
    dot = sum(vec_a[word] * vec_b[word] for word in common)
    mag_a = math.sqrt(sum(value * value for value in vec_a.values()))
    mag_b = math.sqrt(sum(value * value for value in vec_b.values()))
    return dot / (mag_a * mag_b) if mag_a and mag_b else 0.0


def _overlap_snippet(text_a: str, text_b: str) -> str:
    words_b = set(re.findall(r"\w+", (text_b or "").lower()))
    words = (text_a or "").split()
    overlap = [word for word in words if word.lower().strip(".,;:()[]{}") in words_b]
    if len(overlap) >= 8:
        return "... " + " ".join(overlap[:40]) + " ..."
    return (text_a or "")[:300]


def _match_scope(row: dict, batch_id: str | None, assignment_id: str | None, subject_id: str | None) -> str:
    if batch_id and str(row.get("batch_id")) == batch_id:
        return "same_batch"
    if assignment_id and str(row.get("assignment_id")) == assignment_id:
        return "same_assignment"
    if subject_id and str(row.get("subject_id")) == subject_id:
        return "same_subject"
    return "unknown"


async def _retrieve_subject_kb_context(
    *,
    llm,
    org_id: str,
    subject_id: str,
    assignment_prompt: str,
    raw_rubric: str,
    submission_text: str,
    course_weight: int,
    ai_weight: int,
) -> str:
    query = "\n\n".join([
        "Assignment prompt:",
        assignment_prompt[:2_000] or "No assignment prompt provided.",
        "Rubric / evaluation criteria:",
        raw_rubric[:2_000],
        "Student submission preview:",
        submission_text[:3_000],
    ])
    try:
        chunks = await retrieve_and_rerank(
            llm=llm,
            org_id=org_id,
            subject_id=subject_id,
            query_text=query,
            top_k=8,
            candidate_limit=30,
        )
    except Exception as e:
        logger.warning("Subject KB retrieval failed for subject %s: %s", subject_id, e)
        raise RuntimeError("Subject knowledge-base retrieval failed. Retry after indexing is ready.") from e

    if not chunks:
        return (
            "=== SUBJECT KNOWLEDGE BASE CONTEXT ===\n"
            "No relevant subject KB chunks were retrieved. Grade using the rubric and general AI expertise."
        )

    parts = [
        "=== SUBJECT KNOWLEDGE BASE CONTEXT ===",
        f"Grounding weights selected by instructor: {course_weight}% retrieved course material, {ai_weight}% AI expertise.",
        "Rubric/evaluation criteria remain mandatory and override both sources.",
        "Use these retrieved chunks for course-specific facts. If a chunk is irrelevant, ignore it.",
    ]
    for i, chunk in enumerate(chunks, start=1):
        parts.append(
            f"\n--- Retrieved KB chunk {i} | id={chunk.get('id')} | relevance={float(chunk.get('score', 0.0)):.3f} ---"
        )
        parts.append(f"Source: {chunk.get('title', 'Course reference')} | retrieval: {chunk.get('method', 'semantic')}")
        parts.append(str(chunk.get("text", ""))[:1_600])

    return "\n".join(parts)


async def _mark_failed(
    org_id: str,
    submission_id: str,
    batch_id: str | None,
    message: str = "Grading failed before a report could be generated.",
) -> None:
    async with get_conn(org_id) as conn:
        await conn.execute(
            "UPDATE submissions SET status = 'failed' WHERE id = $1", submission_id
        )
        if batch_id:
            await conn.execute(
                "UPDATE batches SET processed_files = processed_files + 1 WHERE id = $1",
                batch_id,
            )
    await _set_progress(
        org_id,
        submission_id,
        "failed",
        100,
        message,
    )


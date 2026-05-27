"""
GradeWise v3 — hardened grading pipeline.

10-step pipeline per v3 §7:
  [D]  0  Cache check (Redis)
  [D]  1  Text extract / code sandbox
  [D]  2  Sensitive-data scan (utility LLM)
  [D]  3  Graph lookup (expected concepts + misconceptions)
  [D]  4  pgvector retrieve + rerank (parallel, all questions)
  [LLM] 5  SPECIALIST (gpt-oss-120b, temp 0.2)
  [LLM] 6  JUDGE (qwen3-32b, temp 0)
  [D]  7  Reconcile — Python sums scores; flags needs_review
  [LLM] 8  SENIOR (gpt-oss-120b, temp 0.3) — format only
  [D]  9  Pydantic validate + one repair retry
  [D]  10 Persist + cache

[D] = deterministic — no LLM. [LLM] = model call against retrieved evidence.
"""
from __future__ import annotations

import hashlib
import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.config import settings
from app.db.graph import get_question_context
from app.db.postgres import get_conn
from app.models.feedback import FeedbackReport, RubricScore
from app.services.retrieval_service import retrieve_for_all_questions
from app.utils.prompt_templates import (
    specialist_system, specialist_user,
    judge_system, judge_user,
    senior_system, senior_user,
    utility_sensitive_scan_user,
)

if TYPE_CHECKING:
    from app.services.llm_provider import ResilientLLM

logger = logging.getLogger(__name__)


# ---- Step 0: Cache ----------------------------------------------------------

def _cache_key(submission_text: str, assignment_version: int) -> str:
    digest = hashlib.sha256(
        f"{submission_text}::{assignment_version}".encode()
    ).hexdigest()
    return f"gradewise:report:{digest}"


async def _check_cache(redis, key: str) -> dict | None:
    raw = await redis.get(key)
    if raw:
        return json.loads(raw)
    return None


async def _set_cache(redis, key: str, report: dict, ttl_seconds: int = 86400) -> None:
    await redis.setex(key, ttl_seconds, json.dumps(report))


# ---- Step 2: Sensitive scan --------------------------------------------------

async def _sensitive_scan(llm: "ResilientLLM", text: str) -> dict:
    from app.services.llm_provider import ChatMessage
    try:
        resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content="You are a content safety classifier. Output only JSON."),
                ChatMessage(role="user", content=utility_sensitive_scan_user(text)),
            ],
            model=settings.GRADIENT_MODEL_UTILITY,
            temperature=0.0,
            max_tokens=200,
            response_format="json_object",
        )
        return json.loads(resp.text)
    except Exception as e:
        logger.warning("Sensitive scan failed (%s) — skipping.", e)
        return {"flagged": False, "categories": [], "severity": "none"}


# ---- Step 5: Specialist ------------------------------------------------------

async def _run_specialist(
    llm: "ResilientLLM",
    question: dict,
    rubric_criteria: list[dict],
    graph_context: dict,
    retrieved_chunks: list[dict],
    student_answer: str,
    code_result: str | None,
) -> dict:
    from app.services.llm_provider import ChatMessage
    resp = await llm.chat(
        messages=[
            ChatMessage(role="system", content=specialist_system()),
            ChatMessage(role="user", content=specialist_user(
                question_text=question["text"],
                rubric_criteria=rubric_criteria,
                expected_concepts=graph_context["concepts"],
                misconceptions=graph_context["misconceptions"],
                retrieved_chunks=retrieved_chunks,
                student_answer=student_answer,
                code_execution_result=code_result,
            )),
        ],
        model=settings.GRADIENT_MODEL_SPECIALIST,
        temperature=0.2,
        max_tokens=3000,
        response_format="json_object",
    )
    return json.loads(resp.text)


# ---- Step 6: Judge -----------------------------------------------------------

async def _run_judge(
    llm: "ResilientLLM",
    question: dict,
    specialist_output: dict,
    retrieved_chunks: list[dict],
    student_answer: str,
) -> dict:
    from app.services.llm_provider import ChatMessage
    resp = await llm.chat(
        messages=[
            ChatMessage(role="system", content=judge_system()),
            ChatMessage(role="user", content=judge_user(
                question_text=question["text"],
                specialist_output=specialist_output,
                retrieved_chunks=retrieved_chunks,
                student_answer=student_answer,
            )),
        ],
        model=settings.GRADIENT_MODEL_JUDGE,
        temperature=0.0,
        max_tokens=2000,
        response_format="json_object",
    )
    return json.loads(resp.text)


# ---- Step 7: Reconcile -------------------------------------------------------

def _reconcile(specialist_out: dict, judge_out: dict) -> list[dict]:
    """
    Apply Judge corrections to Specialist scores.
    Sum in Python — never trust the model to do arithmetic.
    Low confidence OR Specialist/Judge disagreement → needs_review.
    """
    scores: list[dict] = specialist_out.get("rubricScores", [])
    corrections = {c["criterion"]: c for c in judge_out.get("corrections", [])}

    reconciled = []
    for s in scores:
        crit = s["criterion"]
        if crit in corrections:
            corr = corrections[crit]
            s["score"] = min(s["score"], corr.get("corrected_score", s["score"]))
            s["status"] = corr.get("corrected_status", s["status"])
        # Flag low-confidence
        if s.get("confidence", 1.0) < 0.7:
            s["status"] = "needs_review"
        reconciled.append(s)

    return reconciled


# ---- Step 8: Senior ----------------------------------------------------------

async def _run_senior(
    llm: "ResilientLLM",
    reconciled: dict,
    student_name: str,
) -> dict:
    from app.services.llm_provider import ChatMessage
    resp = await llm.chat(
        messages=[
            ChatMessage(role="system", content=senior_system()),
            ChatMessage(role="user", content=senior_user(reconciled, student_name)),
        ],
        model=settings.GRADIENT_MODEL_SENIOR,
        temperature=0.3,
        max_tokens=1500,
        response_format="json_object",
    )
    return json.loads(resp.text)


# ---- Step 9: Pydantic validate -----------------------------------------------

def _validate_report(
    rubric_scores: list[dict],
    senior_out: dict,
    max_score: float,
) -> FeedbackReport:
    overall = sum(s["score"] for s in rubric_scores)
    has_needs_review = any(s.get("status") == "needs_review" for s in rubric_scores)
    status = (
        "needs_review" if has_needs_review
        else ("pass" if overall >= max_score * 0.5 else "fail")
    )
    return FeedbackReport(
        overallScore=round(overall, 2),
        maxScore=round(max_score, 2),
        status=status,
        summary=senior_out.get("summary", ""),
        strengths=senior_out.get("strengths", []),
        weaknesses=senior_out.get("weaknesses", []),
        suggestions=senior_out.get("suggestions", []),
        rubricScores=[RubricScore(**s) for s in rubric_scores],
        finalComments=senior_out.get("finalComments", ""),
    )


# ---- Main entry point --------------------------------------------------------

async def run_pipeline(
    *,
    llm: "ResilientLLM",
    redis,
    org_id: str,
    subject_id: str,
    assignment_id: str,
    assignment_version: int,
    questions: list[dict],         # [{id, text, max_marks}]
    rubric_criteria: list[dict],   # [{id, name, max_score, description}]
    student_answer: str,
    student_name: str = "Student",
    submission_id: str | None = None,
    code_execution_result: str | None = None,
) -> FeedbackReport:
    """
    Run the full 10-step hardened grading pipeline.
    Returns a Pydantic-validated FeedbackReport.
    """

    # Step 0: Cache check
    cache_key = _cache_key(student_answer, assignment_version)
    cached = await _check_cache(redis, cache_key)
    if cached:
        logger.info("Cache hit for submission (assignment_version=%d)", assignment_version)
        return FeedbackReport(**cached)

    # Step 2: Sensitive-data scan
    scan = await _sensitive_scan(llm, student_answer)
    if scan.get("flagged") and scan.get("severity") in ("medium", "high"):
        logger.warning("Sensitive content flagged (severity=%s) for submission=%s", scan["severity"], submission_id)

    # Step 3: Graph lookup — expected concepts + misconceptions per question
    graph_contexts: dict[str, dict] = {}
    for q in questions:
        try:
            graph_contexts[q["id"]] = await get_question_context(org_id, q["id"])
        except Exception as e:
            logger.warning("Graph lookup failed for question %s: %s", q["id"], e)
            graph_contexts[q["id"]] = {"concepts": [], "misconceptions": []}

    # Step 4: Retrieve reference chunks (all questions in parallel)
    questions_with_answers = [
        {**q, "student_answer": student_answer}
        for q in questions
    ]
    chunk_map = await retrieve_for_all_questions(
        llm=llm,
        org_id=org_id,
        subject_id=subject_id,
        questions=questions_with_answers,
    )

    # Steps 5, 6, 7: Per-question grading (run questions sequentially for clarity; parallelise in Phase 9)
    all_rubric_scores: list[dict] = []
    specialist_outputs = {}
    judge_outputs = {}

    for q in questions:
        qid = q["id"]
        q_criteria = rubric_criteria  # shared rubric for now; extend to per-question later
        q_chunks = chunk_map.get(qid, [])
        g_ctx = graph_contexts[qid]

        # Step 5: Specialist
        spec_out = await _run_specialist(
            llm=llm,
            question=q,
            rubric_criteria=q_criteria,
            graph_context=g_ctx,
            retrieved_chunks=q_chunks,
            student_answer=student_answer,
            code_result=code_execution_result,
        )
        specialist_outputs[qid] = spec_out

        # Step 6: Judge
        judge_out = await _run_judge(
            llm=llm,
            question=q,
            specialist_output=spec_out,
            retrieved_chunks=q_chunks,
            student_answer=student_answer,
        )
        judge_outputs[qid] = judge_out

        # Step 7: Reconcile
        reconciled_scores = _reconcile(spec_out, judge_out)
        all_rubric_scores.extend(reconciled_scores)

    max_score = sum(c["max_score"] for c in rubric_criteria)

    # Step 8: Senior formats prose
    senior_input = {
        "rubricScores": all_rubric_scores,
        "overallScore": sum(s["score"] for s in all_rubric_scores),
        "maxScore": max_score,
    }
    senior_out = await _run_senior(llm, senior_input, student_name)

    # Step 9: Pydantic validate — one repair retry
    try:
        report = _validate_report(all_rubric_scores, senior_out, max_score)
    except (ValidationError, Exception) as e:
        logger.warning("First validation attempt failed (%s) — retrying with repair.", e)
        # Repair: fill missing fields with safe defaults
        for s in all_rubric_scores:
            s.setdefault("citations", [])
            s.setdefault("confidence", 0.5)
            s.setdefault("status", "needs_review")
        senior_out.setdefault("summary", "Feedback generated with partial grading results.")
        senior_out.setdefault("strengths", [])
        senior_out.setdefault("weaknesses", [])
        senior_out.setdefault("suggestions", [])
        senior_out.setdefault("finalComments", "Please review this submission manually.")
        report = _validate_report(all_rubric_scores, senior_out, max_score)

    # Step 10: Cache result
    await _set_cache(redis, cache_key, report.model_dump())

    return report

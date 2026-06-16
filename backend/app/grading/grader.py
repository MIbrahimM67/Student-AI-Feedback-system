"""
GradeWise — Three-Stage Agentic Grading Pipeline.

Implements the Specialist → Judge → Senior pipeline as specified in the
FYP documentation (Section 8: AI Pipeline Design).

Stage 1 — Specialist: Deep analytical assessment, evidence-based scoring.
Stage 2 — Judge:      Audits the Specialist for fairness & hallucinations.
Stage 3 — Senior:     Synthesizes final polished, student-friendly output.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Awaitable, Callable

from app.services.llm_provider import build_llm_from_env, build_dedicated_llm_from_env, ChatMessage
from app.grading.types import Tier, DocumentPayload, PageImage, Criterion, GradingResult
from app.grading import config
from app.grading.rubric import _extract_json

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, str], Awaitable[None]]


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------

def _build_document_context(
    submission: DocumentPayload,
    reference_pages: list[PageImage],
    criteria: list[Criterion],
) -> str:
    """Builds the shared document context block used by all three stages."""
    parts: list[str] = []

    parts.append("=== GRADING CRITERIA ===")
    for c in criteria:
        parts.append(f"- ID: {c.id} | Max Points: {c.max_points}")
        parts.append(f"  Description: {c.description}")
        if c.reference_hint:
            parts.append(f"  Reference Hint: {c.reference_hint}")

    parts.append("\n=== REFERENCE MATERIAL ===")
    for i, ref_page in enumerate(reference_pages):
        if ref_page.extracted_text:
            parts.append(f"--- Reference Page {i + 1} ---")
            parts.append(ref_page.extracted_text)

    parts.append("\n=== STUDENT SUBMISSION ===")
    if submission.text_only and submission.plain_text:
        parts.append(submission.plain_text)
    else:
        for i, sub_page in enumerate(submission.pages):
            parts.append(f"--- Submission Page {i + 1} ---")
            if sub_page.extracted_text:
                parts.append(sub_page.extracted_text)
            elif sub_page.code_ocr_text:
                parts.append(sub_page.code_ocr_text)

    return "\n".join(parts)


SPECIALIST_SYSTEM = """You are an expert academic Specialist — a domain expert with deep subject knowledge.

Your role is to perform a rigorous, evidence-based analysis of the student's submission against the rubric criteria and reference material.

For each criterion:
- Assign a score (0 to max_points) backed by specific evidence quoted from the submission.
- Identify concrete strengths and weaknesses.
- Be thorough and analytical. Do not inflate scores.

Output ONLY valid JSON matching this exact schema:
{
  "per_criterion": {
    "<criterion_id>": {
      "score": <float>,
      "evidence": "<direct quote or specific observation from the submission>",
      "reasoning": "<why this score was assigned>"
    }
  },
  "strengths": ["<specific strength>"],
  "weaknesses": ["<specific weakness or gap>"],
  "initial_feedback": "<analytical summary of the submission quality>"
}"""


JUDGE_SYSTEM = """You are an expert academic Judge — a quality assurance expert responsible for reviewing grading decisions.

Your role is to critically audit the Specialist's assessment for:
- Fairness: Are scores proportional to the actual quality shown?
- Consistency: Are similar quality levels scored similarly across criteria?
- Hallucinations: Did the Specialist cite evidence that is not actually in the submission?
- Unsupported claims: Are all penalties clearly justified?

For each criterion, decide whether to ACCEPT or CORRECT the score with a reason.

Output ONLY valid JSON matching this exact schema:
{
  "per_criterion_review": {
    "<criterion_id>": {
      "original_score": <float>,
      "final_score": <float>,
      "verdict": "ACCEPTED | CORRECTED",
      "correction_reason": "<reason if corrected, otherwise 'Score is fair and well-evidenced'>"
    }
  },
  "issues_found": ["<specific issue detected in the Specialist assessment>"],
  "overall_verdict": "FAIR | NEEDS_REVISION",
  "corrections_summary": "<brief summary of what was changed and why>"
}"""


SENIOR_SYSTEM = """You are a Senior academic feedback synthesizer — the final authority in the grading pipeline.

You receive the Specialist's detailed analysis and the Judge's corrections. Your role is to:
1. Apply the Judge's corrections to produce final scores.
2. Produce a concise instructor-facing report that can be understood in one look.
3. Write polished, student-friendly feedback (encouraging but honest).
4. Generate actionable suggestions for improvement.
5. Preserve the evidence chain so an instructor can quickly see why the grade was assigned.

Output ONLY valid JSON matching this exact schema:
{
  "instructor_brief": "<3-5 sentence executive summary for the instructor: performance level, main evidence, biggest risk, and grading confidence>",
  "verdict": "excellent | good | satisfactory | needs_improvement | high_risk",
  "score_rationale": "<short explanation of why the final score is fair>",
  "per_criterion": {
    "<criterion_id>": {
      "score": <final_score_float>,
      "note": "<one-sentence grading note>",
      "evidence": "<specific evidence or observation from the submission>",
      "action": "<one concrete improvement for this criterion>"
    }
  },
  "student_feedback": "<2-3 paragraph student-friendly overall feedback>",
  "strengths": ["<specific strength worth highlighting>"],
  "weaknesses": ["<specific area needing improvement>"],
  "priority_actions": ["<highest-impact next step for the student>"],
  "suggestions": ["<concrete, actionable suggestion for improvement>"],
  "final_comments": "<one encouraging closing sentence>"
}"""


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


# ---------------------------------------------------------------------------
# Core 3-stage grading function
# ---------------------------------------------------------------------------

async def grade(
    submission: DocumentPayload,
    reference_pages: list[PageImage],
    criteria: list[Criterion],
    tier: Tier,
    reference_sections_used: list[str] | None = None,
    prefer_dedicated: bool = False,
    progress_callback: ProgressCallback | None = None,
) -> GradingResult:
    """
    Three-stage agentic grading pipeline: Specialist → Judge → Senior.

    As specified in FYP documentation Section 8: AI Pipeline Design.
    """
    t_start = time.time()
    reference_sections_used = reference_sections_used or []

    # Select LLM. Groq/dedicated is reserved for routes that actually need the
    # larger context window; normal Tier 0 work stays on DigitalOcean serverless.
    dedicated = build_dedicated_llm_from_env() if prefer_dedicated else None
    if dedicated:
        llm = dedicated
        logger.info("3-Stage pipeline using dedicated LLM (Groq)")
    else:
        llm = build_llm_from_env()
        logger.info("3-Stage pipeline using serverless LLM")

    from app.config import settings
    model_name = settings.DEDICATED_MODEL if (dedicated and llm is dedicated) else config.GEMINI_MODEL

    doc_context = _build_document_context(submission, reference_pages, criteria)
    total_input_tokens = 0
    total_output_tokens = 0

    try:
        # ------------------------------------------------------------------
        # Stage 1 — Specialist
        # Purpose: Deep analytical evidence-based scoring
        # ------------------------------------------------------------------
        if progress_callback:
            await progress_callback(
                "specialist",
                62,
                "Specialist agent is matching evidence to each rubric criterion.",
            )
        logger.info("Stage 1/3 — Specialist: performing evidence-based assessment")
        specialist_resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content=SPECIALIST_SYSTEM),
                ChatMessage(role="user", content=doc_context),
            ],
            model=model_name,
            temperature=0.3,
        )
        specialist_data = _extract_json(specialist_resp.text)
        total_input_tokens += specialist_resp.input_tokens
        total_output_tokens += specialist_resp.output_tokens
        logger.info("Stage 1 complete — Specialist identified %d criteria scores",
                    len(specialist_data.get("per_criterion", {})))

        # ------------------------------------------------------------------
        # Stage 2 — Judge
        # Purpose: Audit for fairness, consistency, hallucination detection
        # ------------------------------------------------------------------
        if progress_callback:
            await progress_callback(
                "judge",
                76,
                "Judge agent is auditing the score for fairness and unsupported claims.",
            )
        logger.info("Stage 2/3 — Judge: auditing Specialist assessment")
        judge_user = (
            f"{doc_context}\n\n"
            f"=== SPECIALIST ASSESSMENT TO REVIEW ===\n"
            f"{json.dumps(specialist_data, indent=2)}"
        )
        judge_resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content=JUDGE_SYSTEM),
                ChatMessage(role="user", content=judge_user),
            ],
            model=model_name,
            temperature=0.1,
        )
        judge_data = _extract_json(judge_resp.text)
        total_input_tokens += judge_resp.input_tokens
        total_output_tokens += judge_resp.output_tokens
        verdict = judge_data.get("overall_verdict", "FAIR")
        corrections = len([
            v for v in judge_data.get("per_criterion_review", {}).values()
            if v.get("verdict") == "CORRECTED"
        ])
        logger.info("Stage 2 complete — Judge verdict: %s, corrections made: %d", verdict, corrections)

        # ------------------------------------------------------------------
        # Stage 3 — Senior
        # Purpose: Synthesize final polished student-friendly report
        # ------------------------------------------------------------------
        if progress_callback:
            await progress_callback(
                "senior",
                88,
                "Senior agent is synthesizing the final grade and feedback.",
            )
        logger.info("Stage 3/3 — Senior: synthesizing final report")
        senior_user = (
            f"=== GRADING CRITERIA ===\n"
            + "\n".join(f"- {c.id}: {c.description} (max {c.max_points} pts)" for c in criteria)
            + f"\n\n=== SPECIALIST ANALYSIS ===\n{json.dumps(specialist_data, indent=2)}"
            + f"\n\n=== JUDGE REVIEW ===\n{json.dumps(judge_data, indent=2)}"
        )
        senior_resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content=SENIOR_SYSTEM),
                ChatMessage(role="user", content=senior_user),
            ],
            model=model_name,
            temperature=0.1,
        )
        senior_data = _extract_json(senior_resp.text)
        total_input_tokens += senior_resp.input_tokens
        total_output_tokens += senior_resp.output_tokens
        logger.info("Stage 3 complete — Senior produced final report")

        # ------------------------------------------------------------------
        # Extract final results from Senior output
        # ------------------------------------------------------------------
        per_criterion_raw = senior_data.get("per_criterion", {})

        # Normalise scores — Senior may return ints or floats
        per_criterion: dict[str, float] = {}
        criteria_notes: dict[str, dict[str, str]] = {}
        for c in criteria:
            raw = per_criterion_raw.get(c.id, 0.0)
            note_payload: dict[str, str] = {}
            if isinstance(raw, dict):
                note_payload = {
                    "note": str(raw.get("note", "")).strip(),
                    "evidence": str(raw.get("evidence", "")).strip(),
                    "action": str(raw.get("action", "")).strip(),
                }
                raw = raw.get("score", 0.0)
            try:
                score = float(raw)
            except (TypeError, ValueError):
                score = 0.0
            # Clamp to valid range
            per_criterion[c.id] = round(min(max(score, 0.0), c.max_points), 1)
            note_payload = {k: v for k, v in note_payload.items() if v}
            if note_payload:
                criteria_notes[c.id] = note_payload

        total_score = sum(per_criterion.values())
        max_score = sum(c.max_points for c in criteria)

        # Build rich feedback string from Senior's structured output
        instructor_brief = str(senior_data.get("instructor_brief", "")).strip()
        verdict = str(senior_data.get("verdict", "")).strip()
        score_rationale = str(senior_data.get("score_rationale", "")).strip()
        strengths = _string_list(senior_data.get("strengths", []))
        weaknesses = _string_list(senior_data.get("weaknesses", []))
        suggestions = _string_list(senior_data.get("suggestions", []))
        priority_actions = _string_list(senior_data.get("priority_actions", []))
        final_comments = str(senior_data.get("final_comments", "")).strip()
        feedback_body = str(
            senior_data.get("student_feedback")
            or senior_data.get("feedback")
            or "No feedback provided."
        ).strip()

        rich_feedback = feedback_body
        if strengths:
            rich_feedback += "\n\n**Strengths:**\n" + "\n".join(f"- {s}" for s in strengths)
        if weaknesses:
            rich_feedback += "\n\n**Areas for Improvement:**\n" + "\n".join(f"- {w}" for w in weaknesses)
        if priority_actions:
            rich_feedback += "\n\n**Priority Actions:**\n" + "\n".join(f"- {a}" for a in priority_actions)
        if suggestions:
            rich_feedback += "\n\n**Suggestions:**\n" + "\n".join(f"- {s}" for s in suggestions)
        if final_comments:
            rich_feedback += f"\n\n{final_comments}"

        latency_ms = int((time.time() - t_start) * 1000)
        est_cost_usd = (total_input_tokens * 0.075 / 1e6) + (total_output_tokens * 0.3 / 1e6)

        logger.info(
            "3-Stage grading complete — score=%.1f/%.1f, latency=%dms, "
            "tokens_in=%d, tokens_out=%d, judge_corrections=%d",
            total_score, max_score, latency_ms,
            total_input_tokens, total_output_tokens, corrections
        )

        return GradingResult(
            score=total_score,
            max_score=max_score,
            per_criterion=per_criterion,
            feedback=rich_feedback,
            tier_used=tier,
            reference_sections_used=reference_sections_used,
            latency_ms=latency_ms,
            est_cost_usd=est_cost_usd,
            instructor_brief=instructor_brief,
            student_feedback=feedback_body,
            verdict=verdict,
            score_rationale=score_rationale,
            strengths=strengths,
            weaknesses=weaknesses,
            suggestions=suggestions,
            priority_actions=priority_actions,
            criteria_notes=criteria_notes,
        )

    except Exception as e:
        logger.error("3-Stage grading pipeline failed: %s", e, exc_info=True)
        return GradingResult(
            score=0.0,
            max_score=sum(c.max_points for c in criteria),
            per_criterion={},
            feedback=f"Grading pipeline encountered an error: {e}",
            tier_used=tier,
            reference_sections_used=reference_sections_used,
            latency_ms=int((time.time() - t_start) * 1000),
            est_cost_usd=0.0,
        )

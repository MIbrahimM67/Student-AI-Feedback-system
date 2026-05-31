"""
GradeWise — Single Grading Entrypoint (Used by all tiers).

Builds a multimodal Gemini request with submission images + reference images + criteria,
and returns a GradingResult.
"""
from __future__ import annotations

import base64
import json
import logging
import time
from typing import Any

from app.services.llm_provider import build_llm_from_env
from app.grading.types import Tier, DocumentPayload, PageImage, Criterion, GradingResult
from app.grading import config
from app.grading.rubric import _extract_json

logger = logging.getLogger(__name__)


async def grade(
    submission: DocumentPayload,
    reference_pages: list[PageImage],
    criteria: list[Criterion],
    tier: Tier,
    reference_sections_used: list[str] | None = None
) -> GradingResult:
    """
    Core grading function.
    Combines submission and reference pages into a single multimodal prompt.
    """
    t_start = time.time()
    llm = build_llm_from_env()
    reference_sections_used = reference_sections_used or []

    # 1. Build the prompt text
    system_prompt = (
        "You are an expert academic grader. You have been provided with a student's submission "
        "and the correct reference material (e.g. rubric, model answer, textbook chapter).\n\n"
        "Your task is to grade the submission based on the provided reference material against "
        "specific grading criteria.\n\n"
        "Output ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "per_criterion": { "criterion_id": awarded_points (float) },\n'
        '  "feedback": "Detailed overall feedback explaining the score and any mistakes."\n'
        "}\n"
    )

    user_prompt = "=== GRADING CRITERIA ===\n"
    for c in criteria:
        user_prompt += f"- ID: {c.id} (Max Points: {c.max_points})\n  Description: {c.description}\n"
        if c.reference_hint:
            user_prompt += f"  Reference Hint: {c.reference_hint}\n"
    
    # Build text-only prompt — DO serverless (openai-gpt-oss-120b) is text-only;
    # images cause 400. Use the extracted text already stored on each page.
    user_parts: list[str] = [user_prompt]

    user_parts.append("\n=== REFERENCE MATERIAL ===\n")
    for i, ref_page in enumerate(reference_pages):
        user_parts.append(f"--- Reference Page {i+1} ---")
        if ref_page.extracted_text:
            user_parts.append(ref_page.extracted_text)

    user_parts.append("\n=== STUDENT SUBMISSION ===\n")
    if submission.text_only and submission.plain_text:
        user_parts.append(submission.plain_text)
    else:
        for i, sub_page in enumerate(submission.pages):
            user_parts.append(f"--- Submission Page {i+1} ---")
            if sub_page.extracted_text:
                user_parts.append(sub_page.extracted_text)
            elif sub_page.code_ocr_text:
                user_parts.append(sub_page.code_ocr_text)

    user_content = "\n".join(user_parts)

    from app.services.llm_provider import ChatMessage

    try:
        resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_content)
            ],
            model=config.GEMINI_MODEL,
            # NOTE: response_format omitted — DO serverless returns 400 if set
            temperature=0.2
        )


        data: dict[str, Any] = _extract_json(resp.text)
        per_criterion = data.get("per_criterion", {})
        feedback = data.get("feedback", "No feedback provided.")
        
        # Calculate total score and max score
        total_score = sum(per_criterion.get(c.id, 0.0) for c in criteria)
        max_score = sum(c.max_points for c in criteria)

        latency_ms = int((time.time() - t_start) * 1000)
        # est_cost_usd is a placeholder calculation based on tokens
        est_cost_usd = (resp.input_tokens * 0.075 / 1e6) + (resp.output_tokens * 0.3 / 1e6)

        return GradingResult(
            score=total_score,
            max_score=max_score,
            per_criterion=per_criterion,
            feedback=feedback,
            tier_used=tier,
            reference_sections_used=reference_sections_used,
            latency_ms=latency_ms,
            est_cost_usd=est_cost_usd
        )
    except Exception as e:
        logger.error("Grading failed: %s", e)
        return GradingResult(
            score=0.0,
            max_score=sum(c.max_points for c in criteria),
            per_criterion={},
            feedback=f"Grading failed: {e}",
            tier_used=tier,
            reference_sections_used=reference_sections_used,
            latency_ms=int((time.time() - t_start) * 1000),
            est_cost_usd=0.0
        )

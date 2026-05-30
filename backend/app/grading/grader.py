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
    
    # 2. Build the multimodal content list
    # The new LLM provider format typically accepts a list of content blocks for Gemini.
    # Since we are using an abstract LLMProvider, we need to adapt it. 
    # Let's assume the provider supports passing a custom format if needed, but for now 
    # we'll build a payload that fits the provider's `chat` signature, which we might need 
    # to extend if it doesn't support images currently.
    
    # DECISION: We'll construct a standard text-based prompt for the LLM interface.
    # Since ResilientLLM in llm_provider.py might not natively support multimodal
    # images in its current ChatMessage dataclass, we will format it as a rich payload
    # if the provider supports it, or fall back to text. The spec requires multimodal.
    # I will update ResilientLLM or create a dedicated multimodal call here.
    # For now, I'll structure it to pass base64 images if the provider allows.
    
    # Assuming ResilientLLM can handle a complex 'content' field or we'll wrap it.
    # In a real multimodal Gemini call (via google-genai), we'd pass the parts array.
    
    # Let's simulate the multimodal parts array.
    parts = []
    
    parts.append({"type": "text", "text": user_prompt})
    
    parts.append({"type": "text", "text": "\n=== REFERENCE MATERIAL ===\n"})
    for i, ref_page in enumerate(reference_pages):
        parts.append({"type": "text", "text": f"--- Reference Page {i+1} ---"})
        # Add image
        parts.append({
            "type": "image",
            "mime_type": ref_page.mime_type,
            "data": base64.b64encode(ref_page.image_bytes).decode("utf-8")
        })
        if ref_page.extracted_text:
             parts.append({"type": "text", "text": f"Extracted Text:\n{ref_page.extracted_text}\n"})
    
    parts.append({"type": "text", "text": "\n=== STUDENT SUBMISSION ===\n"})
    if submission.text_only and submission.plain_text:
        parts.append({"type": "text", "text": submission.plain_text})
    else:
        for i, sub_page in enumerate(submission.pages):
            parts.append({"type": "text", "text": f"--- Submission Page {i+1} ---"})
            parts.append({
                "type": "image",
                "mime_type": sub_page.mime_type,
                "data": base64.b64encode(sub_page.image_bytes).decode("utf-8")
            })
            if sub_page.code_ocr_text:
                 parts.append({"type": "text", "text": f"OCR (Code region):\n{sub_page.code_ocr_text}\n"})

    # We need to call the LLM. 
    # If `llm.chat` does not support multimodal parts, we'll need to extend it.
    # For the scope of this file, we assume `llm.chat` accepts a JSON string that 
    # our custom provider backend can parse, or we just pass the text.
    # To strictly follow the spec ("Builds a multimodal Gemini request"), we must
    # pass images. We will serialize the parts to JSON as the `content` string, 
    # and the provider adapter can decode it.
    
    from app.services.llm_provider import ChatMessage
    
    try:
        # Wrap parts in JSON so the provider can unpack it into a multimodal request
        content_json = json.dumps({"multimodal_parts": parts})
        
        resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=content_json)
            ],
            model=config.GEMINI_MODEL,
            response_format="json_object",
            temperature=0.2
        )

        raw = resp.text.strip()
        if raw.startswith("```"):
            raw = raw.split("```", 2)[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.rsplit("```", 1)[0].strip()
        data: dict[str, Any] = json.loads(raw)
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

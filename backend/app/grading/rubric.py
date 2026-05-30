"""
GradeWise — Rubric Decomposition.

Splits a monolithic rubric text into discrete Criteria objects.
This should run ONCE per assignment setup, and the result cached.
"""
from __future__ import annotations

import ast
import json
import logging
from typing import Any

from app.services.llm_provider import build_llm_from_env, ChatMessage
from app.grading.types import Criterion
from app.grading import config

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """
    Robustly extract a JSON object from LLM output.
    Uses raw_decode to find the first valid JSON object at any character position,
    handling markdown fences, extra leading chars (rogue '{'), and trailing garbage.
    """
    text = text.strip()

    # Strip markdown code fences first
    if "```" in text:
        parts = text.split("```")
        for part in parts[1::2]:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                text = candidate
                break

    # Use raw_decode to find the FIRST valid JSON object anywhere in the string.
    # This handles extra leading characters like a rogue '{' on line 1.
    decoder = json.JSONDecoder()
    for i, char in enumerate(text):
        if char == '{':
            try:
                result, _ = decoder.raw_decode(text, i)
                return result
            except json.JSONDecodeError:
                continue

    # Last resort: ast.literal_eval for Python-style single-quoted dicts
    try:
        result = ast.literal_eval(text)
        if isinstance(result, dict):
            return result
    except Exception:
        pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}")


async def decompose(rubric_text: str) -> list[Criterion]:
    """
    Decompose a raw rubric text into a list of discrete Criteria using the LLM.
    Falls back to a single generic criterion if decomposition fails or returns empty.
    """
    # Guard: coerce None/empty to a sensible default so slicing never fails
    rubric_text = (rubric_text or "").strip() or "Evaluate the overall quality of the submission."
    llm = build_llm_from_env()

    system_prompt = (
        "You are an expert academic grader. Your task is to decompose the provided "
        "grading rubric into a list of discrete, independent grading criteria.\n"
        "Output ONLY valid JSON matching this schema:\n"
        "{\n"
        '  "criteria": [\n'
        "    {\n"
        '      "id": "short_unique_id (e.g. accuracy_1)",\n'
        '      "description": "Detailed description of what is expected",\n'
        '      "max_points": 5.0\n'
        "    }\n"
        "  ]\n"
        "}\n"
    )

    _fallback = [Criterion(
        id="overall_quality",
        description=f"Evaluate overall quality based on: {rubric_text[:400]}",
        max_points=100.0,
    )]

    try:
        resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=f"Decompose this rubric:\n\n{rubric_text}")
            ],
            model=config.GEMINI_MODEL,
            response_format="json_object",
            temperature=0.0
        )

        data: dict[str, Any] = _extract_json(resp.text)
        logger.info("Rubric decomposed, raw criteria count: %d", len(data.get("criteria", [])))
        criteria_list = data.get("criteria", [])

        result: list[Criterion] = []
        for c in criteria_list:
            result.append(
                Criterion(
                    id=c.get("id", "unknown_id"),
                    description=c.get("description", "No description"),
                    max_points=float(c.get("max_points", 0.0)),
                )
            )

        if not result:
            logger.warning("LLM returned empty criteria list — using generic fallback")
            return _fallback

        return result

    except Exception as e:
        logger.error("Rubric decomposition failed: %s — using fallback", e)
        return _fallback

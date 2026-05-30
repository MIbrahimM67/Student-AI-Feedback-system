"""
GradeWise — Rubric Decomposition.

Splits a monolithic rubric text into discrete Criteria objects.
This should run ONCE per assignment setup, and the result cached.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.services.llm_provider import build_llm_from_env, ChatMessage
from app.grading.types import Criterion
from app.grading import config

import ast
import re

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> dict:
    """
    Robustly extract a JSON object from LLM output that may include:
    - Markdown code fences (```json ... ```)
    - Single-quoted Python dicts
    - Extra text before/after the JSON object
    """
    text = text.strip()

    # 1. Strip markdown code fences
    if "```" in text:
        # Extract content between first ``` and last ```
        parts = text.split("```")
        for part in parts[1::2]:  # odd-indexed parts are inside fences
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{"):
                text = candidate
                break

    # 2. Try standard json.loads
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 3. Try to find the first {...} block via regex and parse it
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        candidate = match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass
        # 4. Last resort — ast.literal_eval handles single-quoted Python dicts
        try:
            result = ast.literal_eval(candidate)
            if isinstance(result, dict):
                return result
        except Exception:
            pass

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}")


async def decompose(rubric_text: str) -> list[Criterion]:
    """
    Decompose a raw rubric text into a list of discrete Criteria using the LLM.
    Returns an empty list if decomposition fails.
    """
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

    try:
        resp = await llm.chat(
            messages=[
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=f"Decompose this rubric:\n\n{rubric_text}")
            ],
            # Utility model is fine for structure extraction
            model=config.GEMINI_MODEL,
            response_format="json_object",
            temperature=0.0
        )

        data: dict[str, Any] = _extract_json(resp.text)
        logger.info("Rubric decomposed successfully into %d criteria", len(data.get("criteria", [])))
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
        return result
    except Exception as e:
        logger.error("Rubric decomposition failed: %s", e)
        return []

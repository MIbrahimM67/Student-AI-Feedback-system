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

logger = logging.getLogger(__name__)


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

        data: dict[str, Any] = json.loads(resp.text)
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

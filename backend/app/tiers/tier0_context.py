"""
GradeWise — Tier 0: Context Stuffing.

The default grading path. Loads the entire reference document as multimodal pages
straight into the context window. No retrieval, no vector search.
"""
from __future__ import annotations

import logging

from app.grading.types import Tier, DocumentPayload, Criterion, GradingResult
from app.grading.grader import grade

logger = logging.getLogger(__name__)


async def grade_tier0(
    submission: DocumentPayload,
    reference_payload: DocumentPayload,
    criteria: list[Criterion]
) -> GradingResult:
    """
    Grade a submission by stuffing the entire reference document into the LLM context.
    """
    logger.info("Executing Tier 0 grading for %s", submission.source_path)

    # In Tier 0, the "sections used" is the entire reference document
    sections_used = ["Full Document"]
    
    return await grade(
        submission=submission,
        reference_pages=reference_payload.pages,
        criteria=criteria,
        tier=Tier.CONTEXT,
        reference_sections_used=sections_used
    )

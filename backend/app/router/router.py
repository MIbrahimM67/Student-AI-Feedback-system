"""
GradeWise — Architecture Router.

Decides which grading tier should handle a submission+reference pair based on
size and structural properties.
"""
from __future__ import annotations

import logging

from app.grading.types import Tier, DocumentPayload
from app.grading import config

logger = logging.getLogger(__name__)


def route(payload: DocumentPayload) -> Tier:
    """
    Route the document payload to the cheapest capable grading tier.
    """
    logger.info("Routing payload: est_tokens=%d, has_structure=%s",
                payload.est_tokens, payload.has_structure)

    if payload.est_tokens <= config.CONTEXT_BUDGET_TOKENS:
        logger.info("Decision: Tier 0 (Context Stuffing)")
        return Tier.CONTEXT
    
    if payload.has_structure:
        logger.info("Decision: Tier 1 (Tree Navigation)")
        return Tier.TREE
    
    logger.info("Decision: Tier 2 (Vector Fallback)")
    return Tier.VECTOR

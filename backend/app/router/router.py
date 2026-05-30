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


def route(sub_payload: DocumentPayload, ref_payload: DocumentPayload) -> Tier:
    """
    Route the document payload to the cheapest capable grading tier.
    """
    combined_tokens = sub_payload.est_tokens + ref_payload.est_tokens
    logger.info("Routing payload: combined_tokens=%d, ref_has_structure=%s",
                combined_tokens, ref_payload.has_structure)

    if combined_tokens <= config.CONTEXT_BUDGET_TOKENS:
        logger.info("Decision: Tier 0 (Context Stuffing)")
        return Tier.CONTEXT
        
    if sub_payload.est_tokens > config.CONTEXT_BUDGET_TOKENS:
        logger.info("Decision: Tier 3 (Map-Reduce Grading)")
        return Tier.MAP_REDUCE
    
    if ref_payload.has_structure:
        logger.info("Decision: Tier 1 (Tree Navigation)")
        return Tier.TREE
    
    logger.info("Decision: Tier 2 (Vector Fallback)")
    return Tier.VECTOR

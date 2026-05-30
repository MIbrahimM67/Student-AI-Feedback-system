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


SERVERLESS_INPUT_CAP = 8192 
TIER0_BUDGET = int(SERVERLESS_INPUT_CAP * 0.8)  # 6553 tokens

def route(sub_payload: DocumentPayload, ref_payload: DocumentPayload) -> Tier:
    """
    Route the document payload to the cheapest capable grading tier.
    """
    combined = sub_payload.est_tokens + ref_payload.est_tokens
    logger.info("Routing payload: combined_tokens=%d, sub_tokens=%d, ref_has_structure=%s", 
                combined, sub_payload.est_tokens, ref_payload.has_structure)

    if combined <= TIER0_BUDGET:
        logger.info("Decision: Tier 0 (Context Stuffing)")
        return Tier.CONTEXT          # full-context, the quality path, for everything that fits
        
    if sub_payload.est_tokens > TIER0_BUDGET:
        logger.info("Decision: Tier 3 (Map-Reduce Grading)")
        return Tier.MAP_REDUCE       # submission itself too big -> Tier 3
        
    if ref_payload.has_structure:
        logger.info("Decision: Tier 1 (Tree Navigation)")
        return Tier.TREE             # Tier 1
        
    logger.info("Decision: Tier 2 (Vector Fallback)")
    return Tier.VECTOR               # reference too big -> Tier 2 RAG

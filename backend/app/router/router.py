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


SERVERLESS_INPUT_CAP = 2_000
TIER0_BUDGET = SERVERLESS_INPUT_CAP  # DigitalOcean serverless ceiling for grading calls
DEDICATED_CONTEXT_CAP = 120_000  # Groq/Llama-3.3-70B: 128k window, leave headroom


def _dedicated_available() -> bool:
    """True when a high-capacity dedicated endpoint is configured."""
    from app.config import settings
    return bool(settings.DEDICATED_INFERENCE_BASE_URL and (
        settings.DEDICATED_INFERENCE_TOKEN
        or any(key.strip() for key in settings.DEDICATED_INFERENCE_TOKENS.split(","))
    ))


def route(sub_payload: DocumentPayload, ref_payload: DocumentPayload) -> Tier:
    """
    Route the document payload to the cheapest capable grading tier.
    """
    combined = sub_payload.est_tokens + ref_payload.est_tokens
    from app.config import settings
    if settings.DOCUMENT_DEMO:
        # Uploaded references are not necessarily indexed. Grade from the actual
        # document, and fail explicitly when the configured model is too small.
        budget = DEDICATED_CONTEXT_CAP if _dedicated_available() else TIER0_BUDGET
        if combined > budget:
            raise ValueError("Document demo requires a configured high-context dedicated model for documents this size")
        return Tier.CONTEXT
    logger.info("Routing payload: combined_tokens=%d, sub_tokens=%d, dedicated=%s",
                combined, sub_payload.est_tokens, _dedicated_available())

    # Small enough for serverless — always Tier 0
    if combined <= TIER0_BUDGET:
        logger.info("Decision: Tier 0 (Context Stuffing) via serverless")
        return Tier.CONTEXT

    # Large doc — use dedicated endpoint (128k context) if available
    if _dedicated_available() and combined <= DEDICATED_CONTEXT_CAP:
        logger.info("Decision: Tier 0 (Context Stuffing) via dedicated endpoint — full %d tokens", combined)
        return Tier.CONTEXT

    # Dedicated not available OR even too big for 128k — fall through to chunked tiers
    if sub_payload.est_tokens > TIER0_BUDGET:
        logger.info("Decision: Tier 3 (Map-Reduce) — no dedicated endpoint available")
        return Tier.MAP_REDUCE

    if ref_payload.has_structure:
        logger.info("Decision: Tier 1 (Tree Navigation)")
        return Tier.TREE

    logger.info("Decision: Tier 2 (Vector Fallback)")
    return Tier.VECTOR

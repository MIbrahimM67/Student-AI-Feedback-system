"""
GradeWise — Single Grading Pipeline Entrypoint.

Wires the ingest → route → decompose → dispatch → log flow.
This replaces the inner logic of the Celery grading task.
"""
from __future__ import annotations

import logging
import time

from app.ingest.ingest import ingest
from app.router.router import route
from app.grading.rubric import decompose
from app.grading.types import Tier, GradingResult
from app.tiers.tier0_context import grade_tier0
from app.tiers.tier1_tree import grade_tier1
from app.tiers.tier2_vector import grade_tier2

logger = logging.getLogger(__name__)


async def grade_submission(
    submission_path: str,
    reference_path: str,
    raw_rubric: str,
    org_id: str,
    subject_id: str
) -> GradingResult:
    """
    End-to-end grading pipeline.
    """
    t_start = time.time()
    logger.info("Starting grading pipeline for submission: %s", submission_path)

    # 1. Ingest submission and reference
    logger.info("Ingesting submission...")
    sub_payload = ingest(submission_path)
    
    logger.info("Ingesting reference...")
    ref_payload = ingest(reference_path)

    # 2. Decompose Rubric
    # Note: In a production setting, this should be cached per assignment_id.
    logger.info("Decomposing rubric...")
    criteria = await decompose(raw_rubric)
    if not criteria:
        raise ValueError("Failed to decompose rubric into criteria.")

    # 3. Route to the appropriate tier based on REFERENCE size/structure
    # The submission size matters for context budget, but the routing decision
    # is primarily driven by whether the reference fits or has structure.
    # We pass the combined est_tokens to the router for Tier 0 checks, but 
    # check has_structure on the reference.
    
    combined_tokens = sub_payload.est_tokens + ref_payload.est_tokens
    
    # We temporarily mock the reference payload to carry the combined token count
    # just for the router decision.
    router_payload = ref_payload
    router_payload.est_tokens = combined_tokens
    
    tier = route(router_payload)

    # 4. Dispatch
    try:
        if tier == Tier.CONTEXT:
            result = await grade_tier0(sub_payload, ref_payload, criteria)
        elif tier == Tier.TREE:
            result = await grade_tier1(sub_payload, ref_payload, criteria)
        elif tier == Tier.VECTOR:
            result = await grade_tier2(
                submission=sub_payload,
                reference_payload=ref_payload,
                criteria=criteria,
                org_id=org_id,
                subject_id=subject_id
            )
        else:
            raise ValueError(f"Unknown tier selected: {tier}")
            
    except Exception as e:
        logger.error("Grading failed in tier %s: %s", tier, e)
        raise

    total_latency_ms = int((time.time() - t_start) * 1000)
    result.latency_ms = total_latency_ms

    # 5. Log structured event (feeds the eval harness and telemetry)
    # DECISION: Using standard Python logger; in production, this could be 
    # a structured JSON log to Datadog/CloudWatch.
    log_event = {
        "event": "grading_completed",
        "submission_path": submission_path,
        "tier_used": result.tier_used.value,
        "score": result.score,
        "max_score": result.max_score,
        "criteria_coverage": len(result.per_criterion) / len(criteria) if criteria else 0,
        "reference_sections_used": result.reference_sections_used,
        "latency_ms": result.latency_ms,
        "est_cost_usd": result.est_cost_usd
    }
    logger.info("GRADING_EVENT: %s", log_event)

    return result

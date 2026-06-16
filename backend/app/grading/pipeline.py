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
from app.tiers.tier3_map_reduce import grade_tier3
from app.grading.grader import ProgressCallback

logger = logging.getLogger(__name__)


async def grade_submission(
    submission_path: str,
    reference_path: str,
    raw_rubric: str,
    org_id: str,
    subject_id: str,
    progress_callback: ProgressCallback | None = None,
) -> GradingResult:
    """
    End-to-end grading pipeline.
    """
    t_start = time.time()
    logger.info("Starting grading pipeline for submission: %s", submission_path)

    # 1. Ingest submission and reference
    logger.info("Ingesting submission...")
    if progress_callback:
        await progress_callback("ingesting_submission", 42, "Preparing the submission for routing.")
    sub_payload = ingest(submission_path)
    
    logger.info("Ingesting reference...")
    if progress_callback:
        await progress_callback("ingesting_reference", 46, "Preparing reference material and rubric context.")
    ref_payload = ingest(reference_path)

    # 2. Decompose Rubric
    # Note: In a production setting, this should be cached per assignment_id.
    logger.info("Decomposing rubric...")
    if progress_callback:
        await progress_callback("decomposing_rubric", 50, "Breaking the rubric into measurable criteria.")
    criteria = await decompose(raw_rubric)
    if not criteria:
        raise ValueError("Failed to decompose rubric into criteria.")

    # 3. Route to the appropriate tier based on REFERENCE size/structure
    # The submission size matters for context budget, but the routing decision
    # is primarily driven by whether the reference fits or has structure.
    # We pass the combined est_tokens to the router for Tier 0 checks, but 
    # check has_structure on the reference.
    tier = route(sub_payload, ref_payload)
    if progress_callback:
        await progress_callback(
            "routing",
            56,
            f"Selected {tier.value} grading route based on document size and structure.",
        )

    # 4. Dispatch
    try:
        if tier == Tier.CONTEXT:
            result = await grade_tier0(sub_payload, ref_payload, criteria, progress_callback=progress_callback)
        elif tier == Tier.TREE:
            result = await grade_tier1(sub_payload, ref_payload, criteria, progress_callback=progress_callback)
        elif tier == Tier.VECTOR:
            result = await grade_tier2(
                submission=sub_payload,
                reference_payload=ref_payload,
                criteria=criteria,
                org_id=org_id,
                subject_id=subject_id,
                progress_callback=progress_callback,
            )
        elif tier == Tier.MAP_REDUCE:
            result = await grade_tier3(sub_payload, ref_payload, criteria, progress_callback=progress_callback)
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

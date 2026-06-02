"""
GradeWise — Tier 3: Map-Reduce Grading.

Splits massive submissions into chunks of pages and grades them sequentially,
incorporating an API cooldown delay to respect rate limits.
"""
from __future__ import annotations

import logging
import asyncio

from app.grading.types import Tier, DocumentPayload, Criterion, GradingResult
from app.grading.grader import grade
from app.router.router import _dedicated_available

logger = logging.getLogger(__name__)

SERVERLESS_CHUNK_SIZE = 4  # pages per chunk for 8k context models
DEDICATED_CHUNK_SIZE = 80  # pages per chunk for 128k context models (Groq)
COOLDOWN_DELAY_S = 3.0  # seconds to wait between chunks


async def grade_tier3(
    submission: DocumentPayload,
    reference_payload: DocumentPayload,
    criteria: list[Criterion]
) -> GradingResult:
    """
    Grade a massive submission by breaking it into chunks and aggregating the scores.
    """
    logger.info("Executing Tier 3 (Map-Reduce) grading for %s", submission.source_path)
    
    # Dynamically select chunk size based on available model capacity
    chunk_size = DEDICATED_CHUNK_SIZE if _dedicated_available() else SERVERLESS_CHUNK_SIZE

    # In Tier 3, we process the student's submission in chunks.
    # We still pass the reference pages (if any) to every chunk, but since Tier 3
    # is usually chosen when the submission itself is massive and reference is empty/small,
    # this is safe.
    
    total_pages = len(submission.pages)
    if total_pages == 0:
        # Fallback if there are no pages (text-only massive submission)
        # For MVP, we pass it to tier0 as a single text block
        # A true text chunker could be added here later.
        logger.warning("Tier 3 received a 0-page text payload. Falling back to 1 chunk.")
        return await grade(
            submission=submission,
            reference_pages=reference_payload.pages,
            criteria=criteria,
            tier=Tier.MAP_REDUCE,
            reference_sections_used=["Full Document"]
        )

    chunks = []
    for i in range(0, total_pages, chunk_size):
        chunks.append(submission.pages[i:i + chunk_size])

    logger.info("Split submission into %d chunks of up to %d pages each", len(chunks), chunk_size)

    chunk_results: list[GradingResult] = []
    
    for idx, page_chunk in enumerate(chunks):
        logger.info("Grading Chunk %d/%d", idx + 1, len(chunks))
        
        # Create a temporary payload for this chunk
        chunk_payload = DocumentPayload(
            source_path=f"{submission.source_path} (Chunk {idx + 1})",
            pages=page_chunk,
            est_tokens=0,  # We don't need exact token counts here
            has_structure=False,
            text_only=submission.text_only,
            plain_text=submission.plain_text if submission.text_only else None
        )
        
        result = await grade(
            submission=chunk_payload,
            reference_pages=reference_payload.pages,
            criteria=criteria,
            tier=Tier.MAP_REDUCE,
            reference_sections_used=[f"Submission Pages {page_chunk[0].page_number}-{page_chunk[-1].page_number}"]
        )
        
        chunk_results.append(result)
        
        if idx < len(chunks) - 1:
            logger.info("Tier 3 cooldown: sleeping for %.1fs to respect API rate limits", COOLDOWN_DELAY_S)
            await asyncio.sleep(COOLDOWN_DELAY_S)

    # --- Reduce Phase: Aggregate Results ---
    final_per_criterion = {}
    combined_feedback = ""
    total_latency = 0
    total_cost = 0.0
    sections_used = []

    for c in criteria:
        final_per_criterion[c.id] = 0.0

    for idx, res in enumerate(chunk_results):
        combined_feedback += f"\n\n### Part {idx + 1} Feedback\n{res.feedback}"
        total_latency += res.latency_ms
        total_cost += res.est_cost_usd
        sections_used.extend(res.reference_sections_used)
        
        for c in criteria:
            final_per_criterion[c.id] += res.per_criterion.get(c.id, 0.0)

    # Average the scores across chunks
    num_chunks = len(chunk_results)
    final_score = 0.0
    for c in criteria:
        avg_score = final_per_criterion[c.id] / num_chunks
        final_per_criterion[c.id] = round(avg_score, 1)
        final_score += final_per_criterion[c.id]

    max_score = sum(c.max_points for c in criteria)

    return GradingResult(
        score=final_score,
        max_score=max_score,
        per_criterion=final_per_criterion,
        feedback=combined_feedback.strip(),
        tier_used=Tier.MAP_REDUCE,
        reference_sections_used=list(set(sections_used)),
        latency_ms=total_latency,
        est_cost_usd=total_cost
    )

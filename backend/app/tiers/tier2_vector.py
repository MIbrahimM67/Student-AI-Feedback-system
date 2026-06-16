"""
GradeWise — Tier 2: Rubric-Anchored Vector Fallback.

Upgrades the existing vector pipeline to retrieve per rubric criterion, rather
than per student paragraph.

Retrieves chunks using pgvector/BGE-M3 + Reranker, then passes the text
(and ideally the original page images if we map chunks to pages) to the grader.
"""
from __future__ import annotations

import logging

from app.services.retrieval_service import retrieve_and_rerank
from app.services.llm_provider import build_llm_from_env
from app.grading.types import Tier, DocumentPayload, Criterion, GradingResult, PageImage
from app.grading.grader import ProgressCallback, grade
from app.grading import config

logger = logging.getLogger(__name__)


async def grade_tier2(
    submission: DocumentPayload,
    reference_payload: DocumentPayload,
    criteria: list[Criterion],
    org_id: str,
    subject_id: str,
    progress_callback: ProgressCallback | None = None,
) -> GradingResult:
    """
    Grade by running vector retrieval *anchored to the rubric criteria*.
    """
    logger.info("Executing Tier 2 grading for %s", submission.source_path)
    llm = build_llm_from_env()

    sections_used = []
    
    # DECISION: In a fully ideal Tier 2, the vector DB chunks would store their
    # origin page_number, so we could load the original PageImages.
    # Currently, `reference_chunks` might not have page_numbers cleanly mapped.
    # We will pass the retrieved text as strings inside the criteria hints,
    # and pass the full reference_payload.pages if it's small enough, or none
    # if it's too big, relying purely on the retrieved text.
    
    for c in criteria:
        # Retrieve using the CRITERION text, not the student's text.
        # This prevents the "recursion retrieves trees" vocabulary collision.
        query = f"{c.description}"
        
        try:
            if progress_callback:
                await progress_callback(
                    "retrieving_reference",
                    58,
                    f"Retrieving reference evidence for {c.id}.",
                )
            chunks = await retrieve_and_rerank(
                llm=llm,
                org_id=org_id,
                subject_id=subject_id,
                query_text=query,
                top_k=config.TIER2_TOP_K,
                candidate_limit=config.TIER2_CANDIDATE_LIMIT
            )
            
            if chunks:
                retrieved_text = "\n\n".join(chunk["text"] for chunk in chunks)
                c.reference_hint = f"Retrieved context:\n{retrieved_text}"
                sections_used.append(f"{c.id}: {len(chunks)} chunks retrieved")
            else:
                c.reference_hint = "No relevant context found in vector DB."
                sections_used.append(f"{c.id}: 0 chunks retrieved")
                
        except Exception as e:
            logger.error("Tier 2 retrieval failed for criterion %s: %s", c.id, e)
            c.reference_hint = "Retrieval error."
            sections_used.append(f"{c.id}: error")

    # In Tier 2, the text context is baked into the criteria hints.
    # We still pass the reference pages in case the model needs visual context
    # (if it's not too massive, otherwise we'd pass an empty list).
    # Since Tier 2 is for unstructured/massive docs, passing all pages might blow
    # the context budget.
    # DECISION: We pass an empty list for reference_pages to avoid OOM, relying
    # entirely on the retrieved text injected into `c.reference_hint`.
    
    return await grade(
        submission=submission,
        reference_pages=[],  # See decision above
        criteria=criteria,
        tier=Tier.VECTOR,
        reference_sections_used=sections_used,
        progress_callback=progress_callback,
    )

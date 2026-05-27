"""
GradeWise v3 — retrieval service.

Hybrid search: pgvector cosine search (subject-scoped) → BGE Reranker → top-k.
Every returned chunk carries its chunk_id so the pipeline can cite it.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from app.db.vectors import similarity_search
from app.config import settings

if TYPE_CHECKING:
    from app.services.llm_provider import ResilientLLM

logger = logging.getLogger(__name__)


async def retrieve_and_rerank(
    llm: "ResilientLLM",
    org_id: str,
    subject_id: str,
    query_text: str,
    top_k: int = 6,
    candidate_limit: int = 20,
) -> list[dict]:
    """
    1. Embed the query via BGE-M3.
    2. Cosine search reference_chunks filtered to subject_id (top 20).
    3. Rerank with BGE Reranker — keep top_k.
    Returns chunk dicts with id, text, score, concept_ids.
    """
    # Step 1: embed query
    embeddings = await llm.embed(
        texts=[query_text],
        model=settings.GRADIENT_EMBED_MODEL,
    )
    query_vec = embeddings[0]

    # Step 2: pgvector search (local DB call — fast)
    candidates = await similarity_search(
        org_id=org_id,
        subject_id=subject_id,
        query_embedding=query_vec,
        limit=candidate_limit,
    )

    if not candidates:
        logger.warning("No reference chunks found for subject_id=%s", subject_id)
        return []

    # Step 3: rerank
    try:
        doc_texts = [c["text"] for c in candidates]
        ranked = await llm.rerank(
            query=query_text,
            documents=doc_texts,
            model=settings.GRADIENT_RERANK_MODEL,
            top_k=top_k,
        )
        # ranked = [(original_index, score), ...]
        return [
            {
                "id": str(candidates[idx]["id"]),
                "text": candidates[idx]["text"],
                "score": score,
                "concept_ids": candidates[idx].get("concept_ids", []),
            }
            for idx, score in ranked
        ]
    except Exception as e:
        logger.warning("Reranker failed (%s) — returning top-%d by cosine score.", e, top_k)
        return [
            {
                "id": str(c["id"]),
                "text": c["text"],
                "score": c.get("score", 0.0),
                "concept_ids": c.get("concept_ids", []),
            }
            for c in candidates[:top_k]
        ]


async def retrieve_for_all_questions(
    llm: "ResilientLLM",
    org_id: str,
    subject_id: str,
    questions: list[dict],   # [{id, text, student_answer}]
    top_k: int = 6,
) -> dict[str, list[dict]]:
    """
    Retrieve reference chunks for all questions IN PARALLEL.
    Returns {question_id: [chunks]}.
    """
    async def _fetch(q: dict) -> tuple[str, list[dict]]:
        # Combine question + student answer for richer query
        query = f"{q['text']}\n\n{q.get('student_answer', '')}"
        chunks = await retrieve_and_rerank(
            llm=llm,
            org_id=org_id,
            subject_id=subject_id,
            query_text=query,
            top_k=top_k,
        )
        return q["id"], chunks

    results = await asyncio.gather(*[_fetch(q) for q in questions])
    return dict(results)

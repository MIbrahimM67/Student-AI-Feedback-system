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
from app.db.postgres import get_conn
from app.services.llm_provider import build_embedding_llm_from_env

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
    embedder = build_embedding_llm_from_env()
    if settings.DOCUMENT_DEMO or embedder is None:
        return await retrieve_text_chunks(org_id,subject_id,query_text,top_k,candidate_limit)
    embeddings = await embedder.embed(texts=[query_text],model=settings.GRADIENT_EMBED_MODEL)
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
        ranked = await embedder.rerank(
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



async def retrieve_text_chunks(org_id: str, subject_id: str, query_text: str, top_k: int=6, candidate_limit: int=30) -> list[dict]:
    """Subject-scoped, cited full-text retrieval; no synthetic semantic vectors."""
    import re
    terms = list(dict.fromkeys(re.findall(r"[^\W_]+",query_text.lower())))[:80]
    if not terms:
        return []
    query = " | ".join(terms)
    async with get_conn(org_id) as conn:
        rows = await conn.fetch(
            "SELECT rc.id,rc.text,rc.concept_ids,rm.title,rm.id as reference_id,rm.index_method,"
            "ts_rank_cd(to_tsvector('simple',rc.text),to_tsquery('simple',$2)) as score "
            "FROM reference_chunks rc JOIN reference_materials rm ON rm.id=rc.reference_id "
            "WHERE rc.subject_id=$1 AND rm.index_status='embedded' "
            "AND to_tsvector('simple',rc.text) @@ to_tsquery('simple',$2) "
            "ORDER BY score DESC,rc.id LIMIT $3",subject_id,query,min(candidate_limit,30),
        )
    return [dict(row, id=str(row['id']),method='full_text') for row in rows[:top_k]]

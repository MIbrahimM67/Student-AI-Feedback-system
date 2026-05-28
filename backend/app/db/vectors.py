"""
GradeWise v3 — pgvector helpers.

All vector ops go through this module so the retrieval pattern
(subject-scoped cosine search → rerank) stays consistent.
"""
from __future__ import annotations

import json
import logging
from typing import Sequence
from uuid import UUID

from app.db.postgres import get_conn

logger = logging.getLogger(__name__)


async def upsert_reference_chunks(
    org_id: str,
    subject_id: str,
    reference_id: str,
    doc_type: str,
    chunks: list[dict],  # [{chunk_index, text, embedding, concept_ids}]
) -> int:
    """
    Insert reference chunks with embeddings into reference_chunks.
    Returns the number of rows inserted.
    """
    if not chunks:
        return 0

    async with get_conn(org_id) as conn:
        await conn.executemany(
            """
            INSERT INTO reference_chunks
              (org_id, subject_id, reference_id, doc_type, chunk_index,
               text, embedding, concept_ids)
            VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8::uuid[])
            ON CONFLICT DO NOTHING
            """,
            [
                (
                    org_id,
                    subject_id,
                    reference_id,
                    doc_type,
                    c["chunk_index"],
                    c["text"],
                    json.dumps(c["embedding"]),       # asyncpg accepts JSON str for vector
                    c.get("concept_ids", []),
                )
                for c in chunks
            ],
        )
    return len(chunks)


async def similarity_search(
    org_id: str,
    subject_id: str,
    query_embedding: list[float],
    limit: int = 20,
) -> list[dict]:
    """
    Cosine similarity search within a single subject's reference chunks.
    Always filtered by subject_id — never cross-subject leakage.
    Returns rows sorted by cosine distance (closest first).
    """
    async with get_conn(org_id) as conn:
        rows = await conn.fetch(
            """
            SELECT id, chunk_index, text, concept_ids,
                   1 - (embedding <=> $2::vector) AS score
            FROM reference_chunks
            WHERE subject_id = $1
            ORDER BY embedding <=> $2::vector
            LIMIT $3
            """,
            subject_id,
            json.dumps(query_embedding),
            limit,
        )
    return [dict(r) for r in rows]


async def upsert_submission_chunks(
    org_id: str,
    submission_id: str,
    batch_id: str | None,
    chunks: list[dict],  # [{chunk_index, text, embedding}]
) -> int:
    """Insert student submission chunks for plagiarism detection."""
    if not chunks:
        return 0

    async with get_conn(org_id) as conn:
        await conn.executemany(
            """
            INSERT INTO submission_chunks
              (org_id, submission_id, batch_id, chunk_index, text, embedding)
            VALUES ($1, $2, $3, $4, $5, $6::vector)
            ON CONFLICT DO NOTHING
            """,
            [
                (
                    org_id,
                    submission_id,
                    batch_id,
                    c["chunk_index"],
                    c["text"],
                    json.dumps(c["embedding"]),
                )
                for c in chunks
            ],
        )
    return len(chunks)


async def internal_plagiarism_search(
    org_id: str,
    batch_id: str,
    submission_id: str,
    query_embedding: list[float],
    top_k: int = 5,
) -> list[dict]:
    """
    Find similar submission chunks WITHIN the same batch (classmate copying).
    Excludes the submission's own chunks.
    """
    async with get_conn(org_id) as conn:
        rows = await conn.fetch(
            """
            SELECT submission_id, chunk_index, text,
                   1 - (embedding <=> $3::vector) AS score
            FROM submission_chunks
            WHERE batch_id = $1
              AND submission_id != $2
            ORDER BY embedding <=> $3::vector
            LIMIT $4
            """,
            batch_id,
            submission_id,
            json.dumps(query_embedding),
            top_k,
        )
    return [dict(r) for r in rows]

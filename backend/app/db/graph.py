"""
GradeWise v3 — relational knowledge graph.

Models the same edges as Apache AGE would, but as plain Postgres tables.
Identical grading behaviour; swap to Cypher later without touching pipeline code.

Graph structure:
  (Question)      -[:EXPECTS]->       (Concept)
  (RubricCriterion) -[:ASSESSES]->   (Concept)
  (Concept)       -[:COMMON_MISTAKE]-> (Misconception)
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.db.postgres import get_conn

logger = logging.getLogger(__name__)


async def upsert_concept(
    org_id: str,
    subject_id: str,
    name: str,
    definition: str = "",
) -> str:
    """Upsert a concept node; returns its UUID."""
    async with get_conn(org_id) as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO concepts (org_id, subject_id, name, definition)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (subject_id, name)
            DO UPDATE SET definition = EXCLUDED.definition
            RETURNING id
            """,
            org_id, subject_id, name, definition,
        )
    return str(row["id"])


async def link_question_to_concepts(
    question_id: str,
    concept_ids: list[str],
) -> None:
    """Create (Question)-[:EXPECTS]->(Concept) edges."""
    if not concept_ids:
        return
    # Bypass RLS for this junction — org isolation enforced via FK chain.
    async with get_conn() as conn:
        await conn.executemany(
            """
            INSERT INTO question_concepts (question_id, concept_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            [(question_id, cid) for cid in concept_ids],
        )


async def link_criterion_to_concepts(
    criterion_id: str,
    concept_ids: list[str],
) -> None:
    """Create (RubricCriterion)-[:ASSESSES]->(Concept) edges."""
    if not concept_ids:
        return
    async with get_conn() as conn:
        await conn.executemany(
            """
            INSERT INTO rubric_concepts (criterion_id, concept_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            [(criterion_id, cid) for cid in concept_ids],
        )


async def get_question_context(
    org_id: str,
    question_id: str,
) -> dict:
    """
    Graph lookup for a single question.
    Returns:
      - expected concept names + definitions
      - misconceptions per concept
    This is Step 3 of the hardened grading pipeline.
    """
    async with get_conn(org_id) as conn:
        concept_rows = await conn.fetch(
            """
            SELECT c.id, c.name, c.definition
            FROM question_concepts qc
            JOIN concepts c ON c.id = qc.concept_id
            WHERE qc.question_id = $1
            """,
            question_id,
        )
        concept_ids = [str(r["id"]) for r in concept_rows]

        misconception_rows = []
        if concept_ids:
            misconception_rows = await conn.fetch(
                """
                SELECT m.text, c.name AS concept_name
                FROM misconceptions m
                JOIN concepts c ON c.id = m.concept_id
                WHERE m.concept_id = ANY($1::uuid[])
                """,
                concept_ids,
            )

    return {
        "concepts": [
            {"id": str(r["id"]), "name": r["name"], "definition": r["definition"]}
            for r in concept_rows
        ],
        "misconceptions": [
            {"concept": r["concept_name"], "text": r["text"]}
            for r in misconception_rows
        ],
    }

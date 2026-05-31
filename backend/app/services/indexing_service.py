"""
GradeWise v3 — indexing service.

Called by the Celery `index_reference_material` task.

Steps per reference material:
  1. Download file from Firebase Storage
  2. Extract text (PyMuPDF / python-docx / Tesseract)
  3. Chunk text (token-aware, 512-token chunks with 64-token overlap)
  4. Extract concepts per chunk (Utility model)
  5. Embed all chunks in one batch (BGE-M3)
  6. Upsert chunks + embeddings into reference_chunks
  7. Mark reference index_status = 'embedded', update subject kb_status = 'ready'
"""
from __future__ import annotations

import logging
import os
import json
import tempfile
import uuid
from typing import TYPE_CHECKING

from app.config import settings
from app.db.postgres import get_conn
from app.db.vectors import upsert_reference_chunks
from app.db.graph import upsert_concept
from app.services.ocr_service import ocr_service
from app.services.llm_provider import build_llm_from_env, ChatMessage
from app.utils.prompt_templates import utility_concept_extraction_user

logger = logging.getLogger(__name__)

# Chunk settings
CHUNK_TOKENS = 512
OVERLAP_TOKENS = 64
CHARS_PER_TOKEN = 4  # rough approximation


def _chunk_text(text: str, chunk_size: int = CHUNK_TOKENS * CHARS_PER_TOKEN,
                overlap: int = OVERLAP_TOKENS * CHARS_PER_TOKEN) -> list[str]:
    """Split text into overlapping chunks by character count."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return [c for c in chunks if c.strip()]


async def run_indexing(reference_id: str, org_id: str, subject_id: str) -> None:
    """
    Full indexing pipeline for one reference material.
    Called by Celery worker — runs synchronously within an async event loop.
    """
    llm = build_llm_from_env()

    # ---- Step 1: Load reference metadata ------------------------------------
    async with get_conn(org_id) as conn:
        ref = await conn.fetchrow(
            "SELECT * FROM reference_materials WHERE id = $1", reference_id
        )
        if not ref:
            logger.error("Reference %s not found", reference_id)
            return

        await conn.execute(
            "UPDATE reference_materials SET index_status = 'chunking' WHERE id = $1",
            reference_id,
        )
        await conn.execute(
            "UPDATE subjects SET kb_status = 'indexing' WHERE id = $1", subject_id
        )

    file_url = ref["file_url"]
    doc_type = ref["type"]

    # ---- Step 2: Download + extract text ------------------------------------
    tmp_path = None
    try:
        from app.services.local_storage import get_local_path
        local_path = get_local_path(file_url)
        
        if local_path and os.path.exists(local_path):
            # Local Storage Fast Path
            target_path = local_path
        else:
            # Legacy HTTP Download Path (if still using external URLs)
            import httpx
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(file_url)
                resp.raise_for_status()

            ext = os.path.splitext(file_url.split("?")[0])[1] or ".pdf"
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                tmp.write(resp.content)
                tmp_path = tmp.name
            target_path = tmp_path

        filename = os.path.basename(file_url.split("?")[0])
        text = await ocr_service.extract_text(target_path, filename)

    except Exception as e:
        logger.error("Failed to download/extract reference %s: %s", reference_id, e)
        await _mark_failed(org_id, reference_id)
        return
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)

    if not text.strip():
        logger.error("No text extracted from reference %s", reference_id)
        await _mark_failed(org_id, reference_id)
        return

    # ---- Step 3: Chunk -------------------------------------------------------
    raw_chunks = _chunk_text(text)
    logger.info("Reference %s: %d chunks created", reference_id, len(raw_chunks))

    # ---- Step 4: Extract concepts per chunk (Utility model) ------------------
    concept_ids_per_chunk: list[list[str]] = []
    import asyncio as _asyncio
    for chunk_text in raw_chunks:
        try:
            resp = await llm.chat(
                messages=[
                    ChatMessage(role="system", content="You are a concept extractor. Output only JSON."),
                    ChatMessage(role="user", content=utility_concept_extraction_user(chunk_text)),
                ],
                model=settings.GRADIENT_MODEL_UTILITY,
                temperature=0.0,
                max_tokens=500,
                response_format="json_object",
            )
            concepts = json.loads(resp.text)
            if not isinstance(concepts, list):
                concepts = concepts.get("concepts", [])

            chunk_concept_ids = []
            for c in concepts[:5]:  # cap at 5 concepts per chunk
                if isinstance(c, dict) and c.get("name"):
                    cid = await upsert_concept(
                        org_id=org_id,
                        subject_id=subject_id,
                        name=c["name"][:120],
                        definition=c.get("definition", "")[:500],
                    )
                    chunk_concept_ids.append(cid)
            concept_ids_per_chunk.append(chunk_concept_ids)
        except Exception as e:
            logger.warning("Concept extraction failed for chunk: %s", e)
            concept_ids_per_chunk.append([])

        # Pace calls to stay within DO serverless RPM limit (~10 RPM)
        await _asyncio.sleep(6)



    # ---- Step 5: Embed all chunks in one batch ------------------------------
    try:
        embeddings = await llm.embed(
            texts=raw_chunks,
            model=settings.GRADIENT_EMBED_MODEL,
        )
    except Exception as e:
        logger.error("Embedding failed for reference %s: %s", reference_id, e)
        await _mark_failed(org_id, reference_id)
        return

    # ---- Step 6: Upsert into reference_chunks --------------------------------
    chunks_payload = [
        {
            "chunk_index": i,
            "text": raw_chunks[i],
            "embedding": embeddings[i],
            "concept_ids": concept_ids_per_chunk[i],
        }
        for i in range(len(raw_chunks))
    ]

    inserted = await upsert_reference_chunks(
        org_id=org_id,
        subject_id=subject_id,
        reference_id=reference_id,
        doc_type=doc_type,
        chunks=chunks_payload,
    )

    # ---- Step 7: Mark complete -----------------------------------------------
    async with get_conn(org_id) as conn:
        await conn.execute(
            """
            UPDATE reference_materials
            SET index_status = 'embedded', chunk_count = $1
            WHERE id = $2
            """,
            inserted, reference_id,
        )
        # Check if all references for this subject are embedded
        pending = await conn.fetchval(
            """
            SELECT COUNT(*) FROM reference_materials
            WHERE subject_id = $1 AND index_status != 'embedded'
            """,
            subject_id,
        )
        if pending == 0:
            await conn.execute(
                "UPDATE subjects SET kb_status = 'ready' WHERE id = $1", subject_id
            )

    logger.info(
        "Reference %s indexed: %d chunks, %d embedded. Subject kb_status → ready.",
        reference_id, len(raw_chunks), inserted,
    )


async def _mark_failed(org_id: str, reference_id: str) -> None:
    async with get_conn(org_id) as conn:
        await conn.execute(
            "UPDATE reference_materials SET index_status = 'failed' WHERE id = $1",
            reference_id,
        )

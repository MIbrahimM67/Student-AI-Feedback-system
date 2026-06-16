"""
GradeWise Tier 3: evidence-first chunked grading.

Large submissions are reviewed chunk by chunk, but chunks are not graded.
Each chunk extracts evidence, shortcomings, and unresolved missing sections.
Missing material is carried forward into the next chunk's prompt so later
chunks can satisfy it. Only after the last chunk do we run the normal
Specialist -> Judge -> Senior grading pipeline on the aggregated evidence.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.grading import config
from app.grading.grader import ProgressCallback, grade
from app.grading.rubric import _extract_json
from app.grading.types import Criterion, DocumentPayload, GradingResult, Tier
from app.router.router import _dedicated_available
from app.services.llm_provider import ChatMessage, build_dedicated_llm_from_env, build_llm_from_env

logger = logging.getLogger(__name__)

SERVERLESS_CHUNK_SIZE = 4
DEDICATED_CHUNK_SIZE = 80
TEXT_CHUNK_CHARS = 24_000
COOLDOWN_DELAY_S = 3.0


@dataclass
class ChunkReview:
    chunk_label: str
    evidence_by_criterion: dict[str, list[str]] = field(default_factory=dict)
    mistakes_or_shortcomings: list[str] = field(default_factory=list)
    found_requested_sections: list[str] = field(default_factory=list)
    unresolved_missing_sections: list[str] = field(default_factory=list)
    summary: str = ""
    latency_ms: int = 0
    est_cost_usd: float = 0.0


CHUNK_REVIEW_SYSTEM = """You are an evidence review agent in an academic grading pipeline.

You are reviewing ONE chunk of a larger student submission. Do NOT assign marks.

Your job:
1. Extract evidence present in this chunk for each rubric criterion.
2. Identify concrete mistakes, contradictions, weak explanations, or missing support visible in this chunk.
3. If previous chunks requested missing sections, check whether THIS chunk contains them.
4. Do not penalize absent material yet. If a section is still missing, carry it forward in unresolved_missing_sections so the next chunk can search for it.
5. Be faithful to the chunk. Do not invent evidence.

Output ONLY valid JSON matching this schema:
{
  "evidence_by_criterion": {
    "<criterion_id>": ["<specific evidence from this chunk>"]
  },
  "mistakes_or_shortcomings": ["<issue visible in this chunk>"],
  "found_requested_sections": ["<previously requested missing section found in this chunk>"],
  "unresolved_missing_sections": ["<section still not found and should be checked in the next chunk>"],
  "summary": "<brief neutral summary of what this chunk contributes>"
}"""


async def grade_tier3(
    submission: DocumentPayload,
    reference_payload: DocumentPayload,
    criteria: list[Criterion],
    progress_callback: ProgressCallback | None = None,
) -> GradingResult:
    """
    Review chunks for evidence, then run one final agentic grade.
    """
    t_start = time.time()
    logger.info("Executing Tier 3 evidence-first grading for %s", submission.source_path)

    chunks = _build_chunks(submission)
    logger.info("Split submission into %d Tier 3 evidence chunks", len(chunks))

    reviews: list[ChunkReview] = []
    unresolved_missing: list[str] = []
    total_latency = 0
    total_cost = 0.0

    for idx, chunk in enumerate(chunks):
        if progress_callback:
            chunk_percent = 58 + int(((idx + 1) / max(1, len(chunks))) * 18)
            await progress_callback(
                "chunk_review",
                min(chunk_percent, 74),
                f"Reviewing chunk {idx + 1} of {len(chunks)} for evidence and missing sections.",
            )
        review = await _review_chunk(
            chunk=chunk,
            reference_payload=reference_payload,
            criteria=criteria,
            chunk_index=idx,
            total_chunks=len(chunks),
            unresolved_missing=unresolved_missing,
        )
        reviews.append(review)
        unresolved_missing = _dedupe(review.unresolved_missing_sections)
        total_latency += review.latency_ms
        total_cost += review.est_cost_usd

        if idx < len(chunks) - 1:
            logger.info("Tier 3 cooldown: sleeping for %.1fs", COOLDOWN_DELAY_S)
            await asyncio.sleep(COOLDOWN_DELAY_S)

    aggregate_text = _build_aggregate_submission_text(reviews, unresolved_missing, criteria)
    aggregate_payload = DocumentPayload(
        source_path=f"{submission.source_path} (Tier 3 aggregated evidence)",
        pages=[],
        est_tokens=len(aggregate_text) // 4,
        has_structure=False,
        text_only=True,
        plain_text=aggregate_text,
    )

    final_result = await grade(
        submission=aggregate_payload,
        reference_pages=reference_payload.pages,
        criteria=criteria,
        tier=Tier.MAP_REDUCE,
        reference_sections_used=[review.chunk_label for review in reviews],
        prefer_dedicated=_dedicated_available(),
        progress_callback=progress_callback,
    )

    final_result.latency_ms = int((time.time() - t_start) * 1000)
    final_result.est_cost_usd += total_cost
    return final_result


def _build_chunks(submission: DocumentPayload) -> list[DocumentPayload]:
    if submission.text_only and submission.plain_text:
        text = submission.plain_text
        chunks: list[DocumentPayload] = []
        for start in range(0, len(text), TEXT_CHUNK_CHARS):
            part = text[start:start + TEXT_CHUNK_CHARS]
            chunks.append(
                DocumentPayload(
                    source_path=f"{submission.source_path} (chars {start + 1}-{start + len(part)})",
                    pages=[],
                    est_tokens=len(part) // 4,
                    has_structure=False,
                    text_only=True,
                    plain_text=part,
                )
            )
        return chunks or [submission]

    chunk_size = DEDICATED_CHUNK_SIZE if _dedicated_available() else SERVERLESS_CHUNK_SIZE
    chunks = []
    for start in range(0, len(submission.pages), chunk_size):
        page_chunk = submission.pages[start:start + chunk_size]
        if not page_chunk:
            continue
        chunks.append(
            DocumentPayload(
                source_path=f"{submission.source_path} (pages {page_chunk[0].page_number}-{page_chunk[-1].page_number})",
                pages=page_chunk,
                est_tokens=chunk_size * config.TOKENS_PER_PAGE_IMAGE,
                has_structure=False,
                text_only=False,
            )
        )
    return chunks or [submission]


async def _review_chunk(
    *,
    chunk: DocumentPayload,
    reference_payload: DocumentPayload,
    criteria: list[Criterion],
    chunk_index: int,
    total_chunks: int,
    unresolved_missing: list[str],
) -> ChunkReview:
    dedicated = build_dedicated_llm_from_env()
    llm = dedicated or build_llm_from_env()

    from app.config import settings

    model_name = settings.DEDICATED_MODEL if dedicated else config.GEMINI_MODEL
    label = _chunk_label(chunk, chunk_index)
    prompt = _build_chunk_prompt(
        chunk=chunk,
        reference_payload=reference_payload,
        criteria=criteria,
        chunk_index=chunk_index,
        total_chunks=total_chunks,
        unresolved_missing=unresolved_missing,
    )

    t0 = time.perf_counter()
    resp = await llm.chat(
        messages=[
            ChatMessage(role="system", content=CHUNK_REVIEW_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model_name,
        temperature=0.1,
        max_tokens=1800,
        response_format="json_object",
    )
    data = _safe_json(resp.text)

    latency_ms = int((time.perf_counter() - t0) * 1000)
    est_cost = (resp.input_tokens * 0.075 / 1e6) + (resp.output_tokens * 0.3 / 1e6)

    return ChunkReview(
        chunk_label=label,
        evidence_by_criterion=_normalise_evidence(data.get("evidence_by_criterion", {})),
        mistakes_or_shortcomings=_as_string_list(data.get("mistakes_or_shortcomings", [])),
        found_requested_sections=_as_string_list(data.get("found_requested_sections", [])),
        unresolved_missing_sections=_as_string_list(data.get("unresolved_missing_sections", [])),
        summary=str(data.get("summary", "")).strip(),
        latency_ms=latency_ms,
        est_cost_usd=est_cost,
    )


def _build_chunk_prompt(
    *,
    chunk: DocumentPayload,
    reference_payload: DocumentPayload,
    criteria: list[Criterion],
    chunk_index: int,
    total_chunks: int,
    unresolved_missing: list[str],
) -> str:
    parts = [
        f"=== CHUNK POSITION ===\nChunk {chunk_index + 1} of {total_chunks}",
        "=== RUBRIC CRITERIA ===",
    ]
    for criterion in criteria:
        parts.append(f"- {criterion.id} (max {criterion.max_points}): {criterion.description}")
        if criterion.reference_hint:
            parts.append(f"  Reference hint: {criterion.reference_hint}")

    parts.append("\n=== REFERENCE MATERIAL TEXT AVAILABLE ===")
    reference_text = _payload_text(reference_payload)
    parts.append(reference_text[:12_000] if reference_text else "No extracted reference text available.")

    parts.append("\n=== SECTIONS STILL BEING SEARCHED FOR ===")
    if unresolved_missing:
        parts.extend(f"- {item}" for item in unresolved_missing)
    else:
        parts.append("None yet. If this chunk implies important material may appear later, add it to unresolved_missing_sections.")

    parts.append("\n=== CURRENT SUBMISSION CHUNK ===")
    parts.append(_payload_text(chunk) or "[No extracted text was available in this chunk.]")
    return "\n".join(parts)


def _build_aggregate_submission_text(
    reviews: list[ChunkReview],
    unresolved_missing: list[str],
    criteria: list[Criterion],
) -> str:
    parts = [
        "This is an aggregated evidence report from a chunked student submission.",
        "Earlier chunks did not receive marks. The final grade must be based on all evidence below.",
        "Only treat unresolved missing sections as real gaps if they were not found in any later chunk.",
        "",
        "=== RUBRIC CRITERIA ===",
    ]
    for criterion in criteria:
        parts.append(f"- {criterion.id} (max {criterion.max_points}): {criterion.description}")

    parts.append("\n=== AGGREGATED CHUNK EVIDENCE ===")
    for review in reviews:
        parts.append(f"\n--- {review.chunk_label} ---")
        if review.summary:
            parts.append(f"Summary: {review.summary}")
        parts.append("Evidence by criterion:")
        for criterion in criteria:
            evidence = review.evidence_by_criterion.get(criterion.id, [])
            if evidence:
                parts.extend(f"- {criterion.id}: {item}" for item in evidence)
        if review.mistakes_or_shortcomings:
            parts.append("Mistakes or shortcomings observed:")
            parts.extend(f"- {item}" for item in review.mistakes_or_shortcomings)
        if review.found_requested_sections:
            parts.append("Previously missing sections found here:")
            parts.extend(f"- {item}" for item in review.found_requested_sections)

    parts.append("\n=== UNRESOLVED AFTER LAST CHUNK ===")
    if unresolved_missing:
        parts.extend(f"- {item}" for item in unresolved_missing)
    else:
        parts.append("None.")

    return "\n".join(parts)


def _payload_text(payload: DocumentPayload) -> str:
    if payload.text_only and payload.plain_text:
        return payload.plain_text

    parts: list[str] = []
    for page in payload.pages:
        page_text = page.extracted_text or page.code_ocr_text or ""
        if page_text:
            parts.append(f"--- Page {page.page_number} ---\n{page_text}")
    return "\n\n".join(parts)


def _chunk_label(chunk: DocumentPayload, chunk_index: int) -> str:
    if chunk.pages:
        return f"Submission pages {chunk.pages[0].page_number}-{chunk.pages[-1].page_number}"
    return f"Submission text chunk {chunk_index + 1}"


def _safe_json(text: str) -> dict[str, Any]:
    try:
        return _extract_json(text)
    except Exception:
        logger.warning("Tier 3 chunk review returned non-JSON output; preserving as summary")
        return {
            "evidence_by_criterion": {},
            "mistakes_or_shortcomings": [],
            "found_requested_sections": [],
            "unresolved_missing_sections": [],
            "summary": text.strip(),
        }


def _normalise_evidence(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _as_string_list(items) for key, items in value.items()}


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

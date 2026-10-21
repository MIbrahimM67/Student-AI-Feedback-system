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
from app.grading.grader import ProgressCallback, grade, _request_stage_json, _build_document_context
from app.grading.rubric import _extract_json
from app.grading.types import Criterion, DocumentPayload, GradingResult, Tier
from app.router.router import _dedicated_available
from app.services.llm_provider import ChatMessage, build_dedicated_llm_from_env, build_llm_from_env

logger = logging.getLogger(__name__)

SERVERLESS_CHUNK_SIZE = 4
DEDICATED_CHUNK_SIZE = 80
TEXT_CHUNK_CHARS = 24_000
COOLDOWN_DELAY_S = 3.0
# Approx. 8,000 tokens at the application's existing four-chars/token estimate.
# Covers the COMPLETE final grading context: rubric, references and evidence.
FINAL_CONTEXT_MAX_CHARS = 32_000


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
5. Compare any carried-forward missing sections with this chunk. Put only sections ACTUALLY supported by this chunk in found_requested_sections; include specific supporting evidence.
6. If this chunk makes new rubric-related sections appear absent, record them in unresolved_missing_sections to be checked in later chunks. These are questions for subsequent chunks, NOT deductions.
7. Include every rubric criterion ID in evidence_by_criterion, using an empty list if this chunk contains no evidence for it.
8. Be faithful to the chunk. Do not invent evidence, and do not assign marks.

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
        unresolved_missing = _carry_unresolved_missing(
            unresolved_missing, review.found_requested_sections,
            review.unresolved_missing_sections,
        )
        total_latency += review.latency_ms
        total_cost += review.est_cost_usd

        if idx < len(chunks) - 1:
            logger.info("Tier 3 cooldown: sleeping for %.1fs", COOLDOWN_DELAY_S)
            await asyncio.sleep(COOLDOWN_DELAY_S)

    if progress_callback:
        await progress_callback(
            "consolidating", 77,
            "Combining chunk evidence into one bounded final grading context.",
        )
    aggregate_text = _build_aggregate_submission_text(reviews, unresolved_missing, criteria)
    original_chars = len(aggregate_text)
    reference_text = reference_payload.plain_text
    final_context_chars = len(_build_document_context(
        DocumentPayload(
            source_path="aggregate", pages=[], est_tokens=len(aggregate_text) // 4,
            has_structure=False, text_only=True, plain_text=aggregate_text,
        ),
        reference_payload.pages, criteria, reference_text,
    ))
    if final_context_chars > FINAL_CONTEXT_MAX_CHARS:
        # One deterministic compaction, never recursive. Preserve ALL distinct
        # evidence and explicit unresolved requirements: duplicate observations
        # can be collapsed, but unique grading evidence must never disappear.
        aggregate_text = _build_compact_aggregate_submission_text(
            reviews, unresolved_missing, criteria,
        )
        final_context_chars = len(_build_document_context(
            DocumentPayload(
                source_path="compact aggregate", pages=[],
                est_tokens=len(aggregate_text) // 4,
                has_structure=False, text_only=True, plain_text=aggregate_text,
            ),
            reference_payload.pages, criteria, reference_text,
        ))
        logger.info(
            "Tier 3 consolidation: original evidence=%d chars, compact=%d chars, "
            "complete final context=%d chars, limit=%d",
            original_chars, len(aggregate_text), final_context_chars, FINAL_CONTEXT_MAX_CHARS,
        )
    if final_context_chars > FINAL_CONTEXT_MAX_CHARS:
        # Never feed an over-budget context back into route() or grade_tier3().
        # Truncating unique evidence would risk unfair marks; fail explicitly.
        raise ValueError(
            "Chunked grading has more unique evidence or reference material than the "
            "safe final context budget. No final grade was issued; instructor review "
            "or a smaller document/reference is required."
        )
    logger.info(
        "Tier 3 final context budget: %d/%d chars (approx. %d tokens), %d chunks",
        final_context_chars, FINAL_CONTEXT_MAX_CHARS, (final_context_chars + 3) // 4, len(chunks),
    )
    aggregate_payload = DocumentPayload(
        source_path=f"{submission.source_path} (Tier 3 aggregated evidence)",
        pages=[],
        est_tokens=(len(aggregate_text) + 3) // 4,
        has_structure=False,
        text_only=True,
        plain_text=aggregate_text,
    )

    final_result = await grade(
        submission=aggregate_payload,
        reference_pages=reference_payload.pages,
        reference_text=reference_text,
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
        start = 0
        while start < len(text):
            end = min(start + TEXT_CHUNK_CHARS, len(text))
            if end < len(text):
                # Prefer paragraph/sentence/word boundaries without exceeding
                # the chunk budget. Keep every character across all chunks.
                lower_bound = start + TEXT_CHUNK_CHARS // 2
                for separator in ("\n\n", "\n", ". ", " "):
                    boundary = text.rfind(separator, lower_bound, end)
                    if boundary >= 0:
                        end = boundary + len(separator)
                        break
            part = text[start:end]
            chunks.append(
                DocumentPayload(
                    source_path=f"{submission.source_path} (chars {start + 1}-{end})",
                    pages=[],
                    est_tokens=(len(part) + 3) // 4,
                    has_structure=False,
                    text_only=True,
                    plain_text=part,
                )
            )
            start = end
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
    resp, data = await _request_stage_json(
        llm,
        stage=f"Chunk {chunk_index + 1}",
        messages=[
            ChatMessage(role="system", content=CHUNK_REVIEW_SYSTEM),
            ChatMessage(role="user", content=prompt),
        ],
        model=model_name,
        section="evidence_by_criterion",
        criterion_ids=[criterion.id for criterion in criteria],
    )
    for key in ("mistakes_or_shortcomings", "found_requested_sections", "unresolved_missing_sections"):
        if not isinstance(data.get(key), list):
            raise ValueError(f"Chunk {chunk_index + 1} did not provide required {key} array")

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
        "Do not deduct marks for a section missing in an early chunk if later chunks supplied evidence.",
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



def _build_compact_aggregate_submission_text(
    reviews: list[ChunkReview],
    unresolved_missing: list[str],
    criteria: list[Criterion],
) -> str:
    """Non-LLM, non-recursive consolidation; never discard distinct evidence.

    Duplicate statements across chunks are merged by exact case-insensitive
    comparison. All distinct criterion evidence, reported mistakes, discovered
    requirements and final unresolved requirements remain in the context.
    """
    parts = [
        "=== CONSOLIDATED CHUNK EVIDENCE (NO CHUNK-LEVEL SCORES) ===",
        "Use evidence from ALL chunks to grade once; early omissions are not "
        "penalties when later chunks provide the material.",
        "Do not invent evidence. Only deduct marks for gaps unresolved after the last chunk.",
    ]
    for criterion in criteria:
        parts.append(f"\n=== CRITERION {criterion.id} (max {criterion.max_points}) ===")
        parts.append(criterion.description)
        unique: dict[str, tuple[str, str]] = {}
        for review in reviews:
            for item in review.evidence_by_criterion.get(criterion.id, []):
                content = item.strip()
                if content:
                    key = content.casefold()
                    if key not in unique:
                        unique[key] = (review.chunk_label, content)
        if unique:
            parts.extend(f"- [{source}] {content}" for source, content in unique.values())
        else:
            parts.append("No supporting evidence was identified in any chunk.")

    for heading, attribute in [
        ("OBSERVED MISTAKES OR SHORTCOMINGS", "mistakes_or_shortcomings"),
        ("PREVIOUSLY MISSING REQUIREMENTS FOUND LATER", "found_requested_sections"),
    ]:
        parts.append(f"\n=== {heading} ===")
        unique_items: dict[str, tuple[str, str]] = {}
        for review in reviews:
            for item in getattr(review, attribute):
                value = item.strip()
                if value and value.casefold() not in unique_items:
                    unique_items[value.casefold()] = (review.chunk_label, value)
        if unique_items:
            parts.extend(f"- [{source}] {value}" for source, value in unique_items.values())
        else:
            parts.append("None.")

    # A summary can be the ONLY evidence for a poorly formed chunk; retain
    # it when the chunk has no extracted criterion evidence or errors.
    summaries = [
        (review.chunk_label, review.summary)
        for review in reviews
        if review.summary and not any(review.evidence_by_criterion.values())
        and not review.mistakes_or_shortcomings
    ]
    if summaries:
        parts.append("\n=== CHUNKS WITHOUT STRUCTURED EVIDENCE ===")
        parts.extend(f"- [{source}] {value}" for source, value in summaries)

    parts.append("\n=== UNRESOLVED AFTER LAST CHUNK ===")
    parts.extend(f"- {item}" for item in _dedupe(unresolved_missing)) if unresolved_missing else parts.append("None.")
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


def _carry_unresolved_missing(
    previously_missing: list[str],
    found_here: list[str],
    newly_missing: list[str],
) -> list[str]:
    """Retain unsatisfied requests until explicitly found in a later chunk.

    Models can omit a previously missing item from an individual chunk's
    unresolved list. Omission is not proof that the material was found.
    """
    resolved = {item.strip().casefold() for item in found_here if item.strip()}
    return _dedupe([
        item for item in [*previously_missing, *newly_missing]
        if item.strip().casefold() not in resolved
    ])


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

"""Sequential evidence-first grading: routing, pending checks, and final-only scoring."""
from unittest.mock import AsyncMock

import pytest

from app.config import settings
from app.grading.types import Criterion, DocumentPayload, GradingResult, Tier
from app.router import router
from app.tiers import tier3_map_reduce


def document(text: str) -> DocumentPayload:
    return DocumentPayload(
        source_path="submission.txt", pages=[], est_tokens=(len(text) + 3) // 4,
        has_structure=False, text_only=True, plain_text=text,
    )


def test_demo_routes_large_submissions_to_sequential_review_even_with_dedicated_llm(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_DEMO", True)
    monkeypatch.setattr(router, "_dedicated_available", lambda: True)
    reference = document("Ground truth for this assignment.")
    assert router.route(document("x" * (4 * 8_000)), reference) == Tier.CONTEXT
    assert router.route(document("x" * (4 * 8_000 + 1)), reference) == Tier.MAP_REDUCE
    assert router.route(document("x" * 59_000), reference) == Tier.MAP_REDUCE


def test_chunk_boundaries_preserve_every_character():
    original = ("Opening paragraph. " * 800 + "\n\n"
                + "Discussion follows. " * 1500 + "\n\n"
                + "Final conclusion. " * 1000)
    chunks = tier3_map_reduce._build_chunks(document(original))
    assert len(chunks) >= 3
    assert all(len(chunk.plain_text) <= tier3_map_reduce.TEXT_CHUNK_CHARS for chunk in chunks)
    assert "".join(chunk.plain_text for chunk in chunks) == original


def test_pending_missing_is_not_dropped_when_intermediate_chunk_omits_it():
    carry = tier3_map_reduce._carry_unresolved_missing
    pending = carry([], [], ["Conclusion"])
    assert pending == ["Conclusion"]
    pending = carry(pending, [], [])
    assert pending == ["Conclusion"]
    pending = carry(pending, ["conclusion"], ["Other missing item"])
    assert pending == ["Other missing item"]


@pytest.mark.asyncio
async def test_final_grading_waits_until_later_chunks_can_resolve_missing(monkeypatch):
    from app.tiers import tier3_map_reduce as module
    criteria = [Criterion(id="reasoning", description="Explain reasoning", max_points=10)]
    text = ("Early background evidence. " * 1850) + "\n\n" + ("Final conclusion evidence. " * 450)
    submission = document(text)
    chunks = module._build_chunks(submission)
    assert len(chunks) >= 2

    observations = []
    async def review_chunk(**kwargs):
        i = kwargs["chunk_index"]
        pending = list(kwargs["unresolved_missing"])
        observations.append((i, pending))
        if i == 0:
            return module.ChunkReview(
                chunk_label="Beginning", evidence_by_criterion={"reasoning": ["Background exists"]},
                unresolved_missing_sections=["Conclusion"],
            )
        if i == len(chunks) - 1:
            assert "Conclusion" in pending
            return module.ChunkReview(
                chunk_label="Final section", evidence_by_criterion={"reasoning": ["Conclusion found"]},
                found_requested_sections=["Conclusion"],
            )
        return module.ChunkReview(
            chunk_label=f"Middle {i}", evidence_by_criterion={"reasoning": ["More analysis"]},
            unresolved_missing_sections=[],
        )

    output = GradingResult(
        score=10, max_score=10, per_criterion={"reasoning": 10},
        feedback="Evidence supports full marks", tier_used=Tier.MAP_REDUCE,
        reference_sections_used=[],
    )
    scorer = AsyncMock(return_value=output)
    monkeypatch.setattr(module, "_review_chunk", review_chunk)
    monkeypatch.setattr(module, "grade", scorer)
    monkeypatch.setattr(module, "_dedicated_available", lambda: True)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())

    result = await module.grade_tier3(submission, document("Ground truth"), criteria)
    assert result.score == 10
    assert len(observations) == len(chunks)
    assert scorer.await_count == 1  # never score individual chunks
    aggregated = scorer.await_args.kwargs["submission"].plain_text
    assert "Conclusion found" in aggregated
    assert "UNRESOLVED AFTER LAST CHUNK" in aggregated
    assert "UNRESOLVED AFTER LAST CHUNK ===\nNone." in aggregated
    assert scorer.await_args.kwargs["tier"] == Tier.MAP_REDUCE


@pytest.mark.asyncio
async def test_invalid_chunk_json_fails_instead_of_silently_losing_evidence(monkeypatch):
    from app.tiers import tier3_map_reduce as module

    class Provider:
        async def chat(self, **_kwargs):
            return type("Response", (), {"text": '{"evidence_by_criterion":', "input_tokens": 100, "output_tokens": 10})()

    monkeypatch.setattr(module, "build_dedicated_llm_from_env", lambda: Provider())
    monkeypatch.setattr(settings, "DEDICATED_MODEL", "example")
    with pytest.raises(ValueError, match="invalid/incomplete JSON after retry"):
        await module._review_chunk(
            chunk=document("Answer"), reference_payload=document("Truth"),
            criteria=[Criterion(id="accuracy", description="Accuracy", max_points=10)],
            chunk_index=0, total_chunks=2, unresolved_missing=[],
        )

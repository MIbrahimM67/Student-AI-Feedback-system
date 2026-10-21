"""Regression coverage: incomplete JSON must not produce a fabricated grade."""
from types import SimpleNamespace

import httpx
import pytest

from app.grading.grader import _request_stage_json
from app.services.llm_provider import ChatMessage


class StubLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def chat(self, **kwargs):
        self.calls.append(kwargs)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(text=item, input_tokens=100, output_tokens=40)


def messages():
    return [ChatMessage(role="system", content="Grade consistently.")]


@pytest.mark.asyncio
async def test_truncated_specialist_json_retries_instead_of_zero_score():
    llm = StubLLM([
        '{"per_criterion":{"c1":',
        '{"per_criterion":{"c1":{"score":6},"c2":{"score":3}}}',
    ])
    _, data = await _request_stage_json(
        llm, stage="Specialist", messages=messages(), model="test-model",
        section="per_criterion", criterion_ids=["c1", "c2"],
    )
    assert data["per_criterion"]["c1"]["score"] == 6
    assert len(llm.calls) == 2
    assert all(call["response_format"] == "json_object" for call in llm.calls)
    assert all(call["max_tokens"] >= 8192 for call in llm.calls)


@pytest.mark.asyncio
async def test_missing_criterion_retries_and_rejects_incomplete_second_output():
    llm = StubLLM([
        '{"per_criterion":{"c1":{"score":5}}}',
        '{"per_criterion":{"c1":{"score":5}}}',
    ])
    with pytest.raises(ValueError, match="invalid/incomplete JSON after retry"):
        await _request_stage_json(
            llm, stage="Senior", messages=messages(), model="test-model",
            section="per_criterion", criterion_ids=["c1", "c2"],
        )
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_provider_json_validation_error_retries_only_once():
    request = httpx.Request("POST", "https://inference.test/chat/completions")
    response = httpx.Response(400, request=request, json={
        "error": {"code": "json_validate_failed", "message": "max completion tokens reached"}
    })
    llm = StubLLM([
        httpx.HTTPStatusError("invalid JSON", request=request, response=response),
        '{"per_criterion_review":{"c1":{"final_score":8}}}',
    ])
    _, data = await _request_stage_json(
        llm, stage="Judge", messages=messages(), model="test-model",
        section="per_criterion_review", criterion_ids=["c1"],
    )
    assert data["per_criterion_review"]["c1"]["final_score"] == 8
    assert len(llm.calls) == 2


@pytest.mark.asyncio
async def test_non_json_related_http_errors_are_not_retried():
    request = httpx.Request("POST", "https://inference.test/chat/completions")
    response = httpx.Response(401, request=request)
    llm = StubLLM([httpx.HTTPStatusError("bad key", request=request, response=response)])
    with pytest.raises(httpx.HTTPStatusError):
        await _request_stage_json(
            llm, stage="Specialist", messages=messages(), model="test-model",
            section="per_criterion", criterion_ids=["c1"],
        )
    assert len(llm.calls) == 1

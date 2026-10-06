"""Execution transport, upload gates and keep-alive; no production credentials."""
import asyncio
import base64
import hashlib
import json
from unittest.mock import AsyncMock

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from fastapi import HTTPException

from app.config import settings
from app.services import remote_code_runner, demo_keepalive
from app.services.demo_limits import code_execution_available, check_submission_type, validate_document


@pytest.mark.parametrize("score", [None, 0.0, 42.0])
def test_export_does_not_turn_missing_integrity_check_into_zero(score, monkeypatch):
    import fitz
    from app.services.report_service import report_service
    monkeypatch.setattr(settings, "DOCUMENT_DEMO", True)
    payload = {"score": 5, "max_score": 10, "summary": "Synthetic report", "plagiarism_similarity_score": score}
    pdf = report_service.generate_student_pdf_bytes(payload, "Demo Student")
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        text = " ".join(page.get_text() for page in doc)
    if score is None:
        assert "Not checked (coming soon)" in text
        assert "0.0% Similarity" not in text
    else:
        assert f"{score}% Similarity" in text


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "DOCUMENT_DEMO", True)
    monkeypatch.setattr(settings, "CODE_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "CODE_RUNNER_URL", "https://example.test/api/internal/code-execution")


def test_demo_coding_requires_enable_flag_and_real_runner(enabled, monkeypatch):
    assert code_execution_available()
    check_submission_type("coding")
    validate_document(b"print(42)", "answer.py", kind="coding")
    validate_document(b"int main(){}", "answer.cc", kind="coding")
    with pytest.raises(HTTPException):
        validate_document(b"PK", "project.zip", kind="coding")
    with pytest.raises(HTTPException):
        validate_document(b"\xff", "answer.py", kind="coding")
    with pytest.raises(HTTPException):
        validate_document(b"a" * 60001, "answer.py", kind="coding")
    monkeypatch.setattr(settings, "CODE_EXECUTION_ENABLED", False)
    assert not code_execution_available()
    with pytest.raises(HTTPException):
        check_submission_type("coding")
    monkeypatch.setattr(settings, "CODE_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "CODE_RUNNER_URL", "")
    assert not code_execution_available()


@pytest.mark.asyncio
async def test_signed_body_and_real_batch_evidence(enabled, monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    monkeypatch.setattr(settings, "FIREBASE_PRIVATE_KEY", pem.replace("\n", "\\n"))
    real_client = httpx.AsyncClient
    calls = []
    def response(request):
        stamp = request.headers["x-gradewise-time"]
        message = f"gradewise-executor-v1\n{stamp}\n{hashlib.sha256(request.content).hexdigest()}".encode()
        key.public_key().verify(base64.b64decode(request.headers["x-gradewise-signature"]), message, padding.PKCS1v15(), hashes.SHA256())
        body = json.loads(request.content)
        calls.append(body)
        return httpx.Response(200, json={"results": [{"stdout": "42", "stderr": "", "exitCode": 0, "isSimulated": False} for _ in body["inputs"]]})
    monkeypatch.setattr(remote_code_runner.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(response)))
    results = await remote_code_runner.execute_tests("print(int(input())+1)", "python", ["41", "5"])
    assert len(results) == 2 and len(calls) == 1
    assert calls[0]["inputs"] == ["41", "5"]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [({"results": []}, 200), ({"results": [{"stdout": "42", "stderr": "", "exitCode": 0, "isSimulated": True}]}, 200), ({"error": "unavailable"}, 503)])
async def test_runner_fails_closed(enabled, monkeypatch, payload, status):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    monkeypatch.setattr(settings, "FIREBASE_PRIVATE_KEY", key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())
    real_client = httpx.AsyncClient
    monkeypatch.setattr(remote_code_runner.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(lambda request: httpx.Response(status, json=payload))))
    with pytest.raises(RuntimeError):
        await remote_code_runner.execute_tests("print(42)", "python", [""])


@pytest.mark.asyncio
async def test_keepalive_calls_lightweight_ping_and_cancels(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://gradewise-document-demo.onrender.com")
    waits, urls = [], []
    async def sleep(seconds):
        waits.append(seconds)
        if seconds == 600:
            raise asyncio.CancelledError()
    real_client = httpx.AsyncClient
    def respond(request):
        urls.append(str(request.url))
        return httpx.Response(200)
    monkeypatch.setattr(demo_keepalive.asyncio, "sleep", sleep)
    monkeypatch.setattr(demo_keepalive.httpx, "AsyncClient", lambda **kw: real_client(**kw, transport=httpx.MockTransport(respond)))
    with pytest.raises(asyncio.CancelledError):
        await demo_keepalive.keepalive()
    assert waits == [30, 600]
    assert urls == ["https://gradewise-document-demo.onrender.com/ping"]


@pytest.mark.asyncio
async def test_keepalive_does_not_ping_arbitrary_hosts(monkeypatch):
    monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://example.test")
    client = AsyncMock()
    monkeypatch.setattr(demo_keepalive.httpx, "AsyncClient", client)
    await demo_keepalive.keepalive()
    client.assert_not_called()

@pytest.mark.asyncio
async def test_execution_evidence_reaches_unchanged_grading_stages(monkeypatch):
    from app.grading import pipeline
    from app.grading.grader import _build_document_context
    from app.grading.types import DocumentPayload, Tier
    payloads = [DocumentPayload('solution.txt', [], 10, False, True, 'print(42)'), DocumentPayload('reference.txt', [], 10, False, True, 'Expected result: 42')]
    monkeypatch.setattr(pipeline, "ingest", lambda _: payloads.pop(0))
    monkeypatch.setattr(pipeline, "decompose", AsyncMock(return_value=[object()]))
    monkeypatch.setattr(pipeline, "route", lambda sub, ref: Tier.CONTEXT)
    async def grade(sub, ref, criteria, **kw):
        context = _build_document_context(sub, [], [], ref.plain_text)
        assert 'print(42)' in context and 'Expected result: 42' in context
        assert 'REAL CODE EXECUTION EVIDENCE' in context and 'Input: 41; Output: 42' in context
        assert 'Exit code 0 alone does not establish correctness' in context
        from app.grading.types import GradingResult
        return GradingResult(10, 10, {'accuracy': 10}, 'Correct', Tier.CONTEXT, [])
    monkeypatch.setattr(pipeline, "grade_tier0", grade)
    result = await pipeline.grade_submission('solution.txt', 'reference.txt', 'Correctness', 'org', 'subject', code_execution_evidence='Input: 41; Output: 42')
    assert result.score == 10

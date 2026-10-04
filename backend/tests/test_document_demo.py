"""Demo gates: no AI/network credentials required; live Postgres tests are optional locally."""
import asyncio
from contextlib import asynccontextmanager
import io
import os
from pathlib import Path
import uuid
import zipfile
import tempfile
from unittest.mock import AsyncMock

os.environ["DOCUMENT_DEMO"] = "true"
os.environ["DB_POOL_MAX_SIZE"] = "4"
os.environ["VISUAL_EXTRACTION_ENABLED"] = "false"

import asyncpg
from fastapi import HTTPException, UploadFile
import httpx
import pytest
import pytest_asyncio

from app.config import settings
from app.db import postgres
from app.services.demo_limits import check_submission_type, read_upload, validate_document
from app.services import file_storage, task_dispatch


def test_coding_and_archives_are_unavailable():
    with pytest.raises(HTTPException, match="Code grading is paused"):
        check_submission_type("coding")
    with pytest.raises(HTTPException) as error:
        validate_document(b"code", "program.py")
    assert error.value.status_code == 415


@pytest.mark.asyncio
async def test_upload_limit_is_checked_before_storing():
    with tempfile.SpooledTemporaryFile(max_size=10 * 1024 * 1024) as file:
        file.write(b"x" * (settings.DEMO_MAX_FILE_MB * 1024 * 1024 + 1))
        file.seek(0)
        upload = UploadFile(file, filename="huge.txt")
        with pytest.raises(HTTPException) as error:
            await read_upload(upload)
    assert error.value.status_code == 413


def test_plain_text_reference_reaches_grading_context():
    from app.grading.grader import _build_document_context
    from app.grading.types import DocumentPayload
    submission = DocumentPayload("answer.txt", [], 10, False, True, "Student answer")
    context = _build_document_context(submission, [], [], "Reference evidence")
    assert "Reference evidence" in context
    assert "Student answer" in context


def test_pdf_page_limit_and_docx_expansion_limit():
    import fitz
    with fitz.open() as pdf:
        for _ in range(settings.DEMO_MAX_PDF_PAGES + 1):
            pdf.new_page()
        with pytest.raises(HTTPException) as error:
            validate_document(pdf.tobytes(), "long.pdf")
        assert error.value.status_code == 422
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as docx:
        docx.writestr("word/document.xml", b"x" * (21 * 1024 * 1024))
    with pytest.raises(HTTPException) as error:
        validate_document(archive.getvalue(), "compressed.docx")
    assert error.value.status_code == 413


@pytest.mark.asyncio
async def test_sandbox_cannot_fall_back_to_simulation(monkeypatch):
    from app.services.code_sandbox_service import CodeSandboxService
    service = CodeSandboxService()
    monkeypatch.setattr(service, "_run_code_simulation", lambda *args: pytest.fail("Simulation executed"))
    with pytest.raises(RuntimeError, match="paused"):
        await service.execute_code("print('hello')", "python")


@pytest.mark.asyncio
async def test_demo_auth_requires_allowed_verified_uid(monkeypatch):
    from app.auth import firebase
    class Auth:
        def verify_id_token(self, token):
            return {"uid": token}
    monkeypatch.setattr(firebase, "_firebase_auth", Auth())
    monkeypatch.setattr(settings, "DEMO_ALLOWED_UIDS", "invited")
    assert firebase.verify_id_token("invited")["uid"] == "invited"
    with pytest.raises(ValueError, match="invite-only"):
        firebase.verify_id_token("uninvited")


@pytest.mark.asyncio
async def test_small_demo_grades_and_decomposes_rubric_without_gradient(monkeypatch):
    import json
    from app.grading.rubric import decompose
    from app.grading.types import DocumentPayload
    from app.tiers.tier0_context import grade_tier0
    from app.services import llm_provider

    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_BASE_URL", "https://api.groq.com/openai/v1")
    monkeypatch.setattr(settings, "DEDICATED_INFERENCE_TOKEN", "test-only-token")
    monkeypatch.setattr(settings, "DEDICATED_MODEL", "llama-3.3-70b-versatile")
    monkeypatch.setattr(settings, "GRADIENT_API_KEY", "")
    requests = []
    responses = iter([
        {"criteria": [{"id": "accuracy", "description": "Factual accuracy", "max_points": 10}]},
        {"per_criterion": {"accuracy": 8}},
        {"overall_verdict": "FAIR"},
        {"per_criterion": {"accuracy": 8}, "final_comments": "Explain the missing evidence."},
    ])
    clients = []
    original_client = httpx.AsyncClient

    def respond(request):
        requests.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(next(responses))}}]})

    def make_client(**kwargs):
        client = original_client(**kwargs, transport=httpx.MockTransport(respond))
        clients.append(client)
        return client

    monkeypatch.setattr(llm_provider.httpx, "AsyncClient", make_client)
    try:
        criteria = await decompose("Factual accuracy: 10 points")
        submission = DocumentPayload("answer.txt", [], 10, False, True, "Student answer")
        reference = DocumentPayload("reference.txt", [], 10, False, True, "Reference evidence")
        result = await grade_tier0(submission, reference, criteria)
        assert result.score == 8
        assert result.max_score == 10
        assert len(requests) == 4
        assert all(url == "https://api.groq.com/openai/v1/chat/completions" for url, _ in requests)
        assert all(body["model"] == "llama-3.3-70b-versatile" for _, body in requests)
    finally:
        for client in clients:
            await client.aclose()


@pytest_asyncio.fixture
async def db(monkeypatch):
    owner_url = os.environ.get("DEMO_TEST_OWNER_URL")
    if not owner_url:
        pytest.skip("Set DEMO_TEST_OWNER_URL to a disposable pgvector database; CI runs this gate")
    owner = await asyncpg.connect(owner_url)
    # Explicit safety gate; never point tests at a real application's database.
    if await owner.fetchval("SELECT current_database()") != "gradewise_demo_test":
        await owner.close()
        pytest.fail("Integration tests only run in the gradewise_demo_test database")
    await owner.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public")
    root = Path(__file__).resolve().parents[2]
    await owner.execute((root / "postgres/init.sql").read_text())
    await owner.execute("ALTER ROLE app_user PASSWORD 'test-only-local-password'")
    await owner.execute((root / "backend/demo_schema.sql").read_text())
    from urllib.parse import urlsplit, urlunsplit
    parts = urlsplit(owner_url)
    app_url = urlunsplit(parts._replace(netloc="app_user:test-only-local-password@" + parts.netloc.rsplit("@", 1)[-1]))
    monkeypatch.setenv("DATABASE_URL", app_url)
    await postgres.init_pool()
    org = uuid.uuid4()
    await owner.execute("INSERT INTO organizations(id,name) VALUES ($1,'Test organization')", org)
    await owner.execute("INSERT INTO users(uid,org_id,email,role) VALUES ('tester',$1,'tester@example.invalid','student')", org)
    try:
        yield owner, org
    finally:
        await task_dispatch.stop_worker()
        await postgres.close_pool()
        await owner.close()


@pytest.mark.asyncio
async def test_storage_survives_pool_restart_and_enforces_tenants(db):
    owner, org = db
    url = await file_storage.save_file(b"A persisted document", "submission.txt", org_id=org, owner_uid="tester")
    await postgres.close_pool()
    await postgres.init_pool()
    async with file_storage.materialize(url, "submission.txt", org) as path:
        assert Path(path).read_bytes() == b"A persisted document"
        temp_path = path
    assert not Path(temp_path).exists()
    with pytest.raises(FileNotFoundError):
        async with file_storage.materialize(url, "submission.txt", uuid.uuid4()):
            pytest.fail("Cross-tenant file was exposed")
    assert await owner.fetchval("SELECT bytes_used FROM demo_storage_budget") > 0
    await owner.execute("DELETE FROM demo_files")
    assert await owner.fetchval("SELECT bytes_used FROM demo_storage_budget") == 0


@pytest.mark.asyncio
async def test_student_document_grades_and_saves_real_schema_report(db, monkeypatch):
    _, org = db
    from app.main import app
    from app.api.student_routes import _get_student_profile
    from app.services import grading_task
    from app.grading.types import GradingResult, Tier
    app.dependency_overrides[_get_student_profile] = lambda: {"uid": "tester", "org_id": org, "role": "student"}
    observed = {}
    async def fake_pipeline(**kwargs):
        observed["text"] = Path(kwargs["submission_path"]).read_text()
        observed["reference"] = Path(kwargs["reference_path"]).read_text()
        return GradingResult(score=75, max_score=100, per_criterion={"quality": 75}, feedback="Evidence-based feedback", tier_used=Tier.CONTEXT, reference_sections_used=[])
    monkeypatch.setattr(grading_task, "route_and_grade", fake_pipeline)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/student/submissions", data={"type": "text"}, files={
                "file": ("answer.txt", b"The document to grade", "text/plain"),
                "reference_file": ("reference.txt", b"Reference evidence", "text/plain"),
            })
            assert response.status_code == 202, response.text
            sid = response.json()["submission_id"]
            # Simulate cold start: no local files or in-memory task required.
            await postgres.close_pool()
            await postgres.init_pool()
            assert await task_dispatch._drain()
            report = await client.get(f"/api/student/submissions/{sid}/feedback")
            assert report.json()["report"]["overallScore"] == 75
            assert report.json()["report"]["summary"] == "Evidence-based feedback"
            assert observed == {"text": "The document to grade", "reference": "Reference evidence"}
            export = await client.get(f"/api/student/submissions/{sid}/pdf")
            assert export.status_code == 200, export.text[:200]
            assert export.content.startswith(b"%PDF")
            blocked = await client.post("/api/student/submissions", data={"type": "coding", "input_text": "print(1)"})
            assert blocked.status_code == 503
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_instructor_single_upload_grades_and_approval_persists(db, monkeypatch):
    owner, org = db
    from app.main import app
    from app.api.instructor_routes import _get_instructor
    from app.services import grading_task
    from app.grading.types import GradingResult, Tier
    subject, assignment = uuid.uuid4(), uuid.uuid4()
    await owner.execute("UPDATE users SET role='instructor' WHERE uid='tester'")
    await owner.execute("INSERT INTO subjects(id,org_id,instructor_id,title) VALUES ($1,$2,'tester','Course')", subject, org)
    await owner.execute("INSERT INTO assignments(id,org_id,subject_id,title,use_subject_kb,internal_similarity_enabled) VALUES ($1,$2,$3,'Assignment',false,false)", assignment, org, subject)
    app.dependency_overrides[_get_instructor] = lambda: {"uid": "tester", "org_id": org, "role": "instructor"}
    async def fake_pipeline(**kwargs):
        assert Path(kwargs["submission_path"]).read_text() == "Instructor uploaded answer"
        return GradingResult(score=75, max_score=100, per_criterion={"quality": 75}, feedback="Instructor review draft", tier_used=Tier.CONTEXT, reference_sections_used=[])
    monkeypatch.setattr(grading_task, "route_and_grade", fake_pipeline)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/instructor/single-upload", data={"assignment_id": str(assignment), "subject_id": str(subject), "student_name": "Demo Student", "type": "text"}, files={"file": ("answer.txt", b"Instructor uploaded answer", "text/plain")})
            assert response.status_code == 202, response.text
            batch = response.json()["batch_id"]
            assert await task_dispatch._drain()
            reports = await client.get(f"/api/instructor/batch/{batch}/reports")
            assert reports.status_code == 200, reports.text
            report = reports.json()["reports"][0]
            assert report["submission_status"] == "graded"
            assert report["approved_at"] is None
            approval = await client.post(f"/api/instructor/batch/{batch}/reports/{report['report_id']}/approve", json={})
            assert approval.status_code == 200, approval.text
            assert approval.json()["status"] == "approved"
            saved = await owner.fetchrow("SELECT approved_by, final_overall_score, published_at FROM feedback_reports WHERE id=$1", uuid.UUID(report["report_id"]))
            assert saved["approved_by"] == "tester"
            assert saved["final_overall_score"] == 75
            assert saved["published_at"] is not None
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_interrupted_job_fails_without_repeating_ai_calls(db, monkeypatch):
    owner, org = db
    sid = uuid.uuid4()
    await owner.execute("INSERT INTO submissions(id,org_id,user_id,type,mode,status) VALUES ($1,$2,'tester','text','single','processing')", sid, org)
    await owner.execute("INSERT INTO demo_jobs(task,target_id,org_id,status) VALUES ('tasks.grade_submission',$1,$2,'running')", sid, org)
    executor = AsyncMock()
    monkeypatch.setattr(task_dispatch, "_execute", executor)
    assert await task_dispatch._drain()
    executor.assert_not_called()
    assert await owner.fetchval("SELECT status FROM submissions WHERE id=$1", sid) == "failed"
    assert await owner.fetchval("SELECT status FROM demo_jobs WHERE target_id=$1", sid) == "failed"


@pytest.mark.asyncio
async def test_rolling_deployment_respects_active_worker_lock(db, monkeypatch):
    owner, _ = db
    await owner.execute("SELECT pg_advisory_lock($1)", task_dispatch.LOCK_ID)
    try:
        assert await task_dispatch._drain() is False
    finally:
        await owner.execute("SELECT pg_advisory_unlock($1)", task_dispatch.LOCK_ID)


@pytest.mark.asyncio
async def test_failed_transaction_does_not_leave_a_job(db):
    owner, org = db
    sid = uuid.uuid4()
    with pytest.raises(RuntimeError):
        async with postgres.get_conn(str(org)) as conn:
            await task_dispatch.dispatch("tasks.grade_submission", [sid, org], conn=conn)
            raise RuntimeError("Submission transaction rolled back")
    assert await owner.fetchval("SELECT count(*) FROM demo_jobs WHERE target_id=$1", sid) == 0

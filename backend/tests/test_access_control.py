"""Access control, publication and policy-warning checks.

Unit tests use small fakes; the Postgres tests reuse the disposable database
fixture from test_document_demo (skipped locally unless DEMO_TEST_OWNER_URL is set).
"""
import json
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

os.environ.setdefault("DOCUMENT_DEMO", "true")
os.environ.setdefault("DB_POOL_MAX_SIZE", "4")
os.environ.setdefault("VISUAL_EXTRACTION_ENABLED", "false")

import httpx
import pytest
from fastapi import HTTPException

from app.config import settings
from app.services.entitlements import has_active_pro, is_verified_faculty

from test_document_demo import db  # noqa: F401  (pytest fixture)

STUDENT = {"uid": "s", "role": "student", "faculty_status": "none", "pro_status": "inactive"}
PENDING = {"uid": "p", "role": "instructor", "faculty_status": "pending", "pro_status": "inactive"}
FACULTY = {"uid": "f", "role": "instructor", "faculty_status": "approved", "pro_status": "inactive"}
PRO = {"uid": "x", "role": "instructor", "faculty_status": "approved", "pro_status": "active"}
ADMIN = {"uid": "a", "role": "admin", "faculty_status": "none", "pro_status": "inactive"}


class FakeConn:
    def __init__(self, row=None, org_id="00000000-0000-0000-0000-000000000001"):
        self.row = row
        self.org_id = org_id
        self.executed = []

    async def fetchval(self, query, *args):
        return self.org_id

    async def fetchrow(self, query, *args):
        self.executed.append((query, args))
        return self.row

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return "UPDATE 1"


def fake_get_conn(conn):
    @asynccontextmanager
    async def _get_conn(org_id=None):
        yield conn
    return _get_conn


# ---- Entitlement rules -------------------------------------------------------

def test_entitlement_matrix():
    assert [is_verified_faculty(u) for u in (STUDENT, PENDING, FACULTY, PRO, ADMIN)] == [False, False, True, True, True]
    assert [has_active_pro(u) for u in (STUDENT, PENDING, FACULTY, PRO, ADMIN)] == [False, False, False, True, True]
    # A Pro flag on an unverified account does not unlock anything.
    assert not has_active_pro({**PENDING, "pro_status": "active"})


@pytest.mark.asyncio
@pytest.mark.parametrize("row,allowed", [(STUDENT, False), (PENDING, False), (FACULTY, True), (ADMIN, True)])
async def test_instructor_dependency_requires_approved_faculty(monkeypatch, row, allowed):
    from app.api import instructor_routes
    monkeypatch.setattr(instructor_routes, "get_conn", fake_get_conn(FakeConn(row={**row, "org_id": "org"})))
    if allowed:
        assert (await instructor_routes._get_instructor("uid"))["role"] == row["role"]
    else:
        with pytest.raises(HTTPException) as denied:
            await instructor_routes._get_instructor("uid")
        assert denied.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("user,allowed", [(FACULTY, False), (PRO, True), (ADMIN, True)])
async def test_pro_dependency(user, allowed):
    from app.api.instructor_routes import _get_pro_instructor
    if allowed:
        assert await _get_pro_instructor(user) is user
    else:
        with pytest.raises(HTTPException) as denied:
            await _get_pro_instructor(user)
        assert denied.value.status_code == 403
        assert "Pro plan" in denied.value.detail


def test_pro_routes_use_pro_dependency():
    from app.main import app
    from app.api.instructor_routes import _get_pro_instructor

    def dependencies(route):
        return {d.call for d in route.dependant.dependencies}

    pro_paths = {
        ("POST", "/api/instructor/batch"),
        ("POST", "/api/instructor/batch/{batch_id}/confirm-names"),
        ("POST", "/api/instructor/batch/{batch_id}/process"),
        ("GET", "/api/instructor/batch/{batch_id}/export/excel"),
        ("GET", "/api/instructor/batch/{batch_id}/export/zip"),
        ("GET", "/api/instructor/reports/{report_id}/pdf"),
    }
    found = set()
    for route in app.routes:
        for method in getattr(route, "methods", set()) or set():
            if (method, getattr(route, "path", "")) in pro_paths:
                assert _get_pro_instructor in dependencies(route), route.path
                found.add((method, route.path))
    assert found == pro_paths


# ---- Billing -----------------------------------------------------------------

@pytest.mark.asyncio
async def test_sandbox_upgrade_requires_verified_faculty(monkeypatch):
    from app.api import billing_routes
    activate = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(billing_routes.stripe_service, "sandbox_activate", activate)
    body = billing_routes.SandboxUpgradeRequest(plan_id="pro")
    for user in (STUDENT, PENDING):
        with pytest.raises(HTTPException) as denied:
            await billing_routes.sandbox_upgrade(body, user)
        assert denied.value.status_code == 403
    activate.assert_not_called()
    assert (await billing_routes.sandbox_upgrade(body, FACULTY))["status"] == "success"
    # Downgrading is always possible.
    assert (await billing_routes.sandbox_upgrade(billing_routes.SandboxUpgradeRequest(plan_id="free"), STUDENT))["status"] == "success"


@pytest.mark.asyncio
async def test_sandbox_upgrade_disabled_with_live_stripe_outside_evaluation(monkeypatch):
    from app.api import billing_routes
    monkeypatch.setattr(type(billing_routes.stripe_service), "is_configured", property(lambda self: True))
    monkeypatch.setattr(billing_routes.stripe_service, "sandbox_activate", AsyncMock(return_value={"status": "success"}))
    monkeypatch.setattr(settings, "DOCUMENT_DEMO", False)
    with pytest.raises(HTTPException) as denied:
        await billing_routes.sandbox_upgrade(billing_routes.SandboxUpgradeRequest(plan_id="pro"), FACULTY)
    assert denied.value.status_code == 403
    monkeypatch.setattr(settings, "DOCUMENT_DEMO", True)
    assert (await billing_routes.sandbox_upgrade(billing_routes.SandboxUpgradeRequest(plan_id="pro"), FACULTY))["status"] == "success"


@pytest.mark.asyncio
async def test_admin_cannot_grant_pro_to_unverified_account(monkeypatch):
    from app.api import admin_routes
    conn = FakeConn(row=STUDENT)
    monkeypatch.setattr(admin_routes, "get_conn", fake_get_conn(conn))
    with pytest.raises(HTTPException) as denied:
        await admin_routes.grant_pro("s", {"uid": "a", "org_id": "org"})
    assert denied.value.status_code == 409
    assert not any("UPDATE users" in q for q, _ in conn.executed)


# ---- Policy warnings ---------------------------------------------------------

@pytest.mark.asyncio
async def test_warning_audit_payload_is_json_text_with_no_fake_actor(monkeypatch):
    from app.services import warning_service as module
    conn = FakeConn(row={"warning_count": 1, "blocked_until": None})
    monkeypatch.setattr(module, "get_conn", fake_get_conn(conn))
    violated, reason = await module.warning_service.scan_and_enforce("org", "student", str(uuid.uuid4()), "Here is the leaked exam")
    assert violated and "leaked exam" in reason
    audit = [(q, a) for q, a in conn.executed if "audit_logs" in q]
    assert len(audit) == 1
    query, args = audit[0]
    assert "'SYSTEM'" not in query and "NULL" in query
    assert isinstance(args[2], str) and json.loads(args[2])["reason"] == reason


@pytest.mark.asyncio
async def test_instructor_upload_violation_is_audited_without_user_warning(monkeypatch):
    from app.services import warning_service as module
    conn = FakeConn()
    monkeypatch.setattr(module, "get_conn", fake_get_conn(conn))
    violated, _ = await module.warning_service.scan_and_enforce("org", None, str(uuid.uuid4()), "cheat sheet attached")
    assert violated
    assert not any("INSERT INTO warnings" in q or "UPDATE users" in q for q, _ in conn.executed)
    assert any("audit_logs" in q for q, _ in conn.executed)


# ---- Postgres-backed checks (run in CI) ---------------------------------------

async def _make_user(owner, org, uid, role="instructor", faculty="approved", pro="inactive"):
    await owner.execute(
        "INSERT INTO users(uid,org_id,email,role,faculty_status,pro_status) VALUES ($1,$2,$3,$4,$5,$6)",
        uid, org, f"{uid}@example.invalid", role, faculty, pro,
    )


@pytest.mark.asyncio
async def test_policy_warnings_persist_and_block_after_three(db):
    owner, org = db
    from app.services.warning_service import warning_service
    for _ in range(3):
        sid = uuid.uuid4()
        await owner.execute("INSERT INTO submissions(id,org_id,user_id,type,mode,status) VALUES ($1,$2,'tester','text','single','processing')", sid, org)
        violated, _ = await warning_service.scan_and_enforce(str(org), "tester", str(sid), "attached: cheat sheet")
        assert violated
    user = await owner.fetchrow("SELECT warning_count, blocked_until FROM users WHERE uid='tester'")
    assert user["warning_count"] == 3
    remaining = user["blocked_until"] - datetime.now(timezone.utc)
    assert timedelta(days=6, hours=23) < remaining <= timedelta(days=7)
    assert await owner.fetchval("SELECT count(*) FROM warnings WHERE user_id='tester' AND status='active'") == 3
    assert await owner.fetchval("SELECT count(*) FROM audit_logs WHERE action='POLICY_VIOLATION' AND actor_uid IS NULL") == 3

    from app.api.student_routes import _get_student_profile
    with pytest.raises(HTTPException) as blocked:
        await _get_student_profile("tester")
    assert blocked.value.status_code == 403

    # Instructor upload: audited, but nobody is warned.
    sid = uuid.uuid4()
    await owner.execute("INSERT INTO submissions(id,org_id,type,mode,status) VALUES ($1,$2,'text','batch','processing')", sid, org)
    violated, _ = await warning_service.scan_and_enforce(str(org), None, str(sid), "leaked exam")
    assert violated
    assert await owner.fetchval("SELECT count(*) FROM warnings") == 3
    assert await owner.fetchval("SELECT count(*) FROM audit_logs WHERE action='POLICY_VIOLATION'") == 4


@pytest.mark.asyncio
async def test_policy_hit_fails_submission_with_reason(db, monkeypatch):
    owner, org = db
    from app.services import grading_task
    sid = uuid.uuid4()
    await owner.execute(
        "INSERT INTO submissions(id,org_id,user_id,type,mode,status,input_text) VALUES ($1,$2,'tester','text','single','uploaded','My answer uses a cheat sheet')",
        sid, org,
    )
    monkeypatch.setattr(grading_task, "route_and_grade", AsyncMock(side_effect=AssertionError("must not grade")))
    monkeypatch.setattr(grading_task, "build_llm_from_env", lambda: None)
    await grading_task.run_grade_submission(str(sid), str(org))
    row = await owner.fetchrow("SELECT status, progress_message FROM submissions WHERE id=$1", sid)
    assert row["status"] == "failed"
    assert "policy scan" in row["progress_message"]
    assert await owner.fetchval("SELECT count(*) FROM feedback_reports WHERE submission_id=$1", sid) == 0
    assert await owner.fetchval("SELECT warning_count FROM users WHERE uid='tester'") == 1


@pytest.mark.asyncio
async def test_student_pdf_requires_publication(db):
    owner, org = db
    from app.main import app
    from app.api.student_routes import _get_student_profile
    sid, rid = uuid.uuid4(), uuid.uuid4()
    await owner.execute("INSERT INTO submissions(id,org_id,user_id,type,mode,status,file_name) VALUES ($1,$2,'tester','text','single','graded','answer.txt')", sid, org)
    await owner.execute(
        "INSERT INTO feedback_reports(id,org_id,submission_id,ai_overall_score,ai_max_score,ai_status,ai_payload) VALUES ($1,$2,$3,7,10,'needs_review',$4)",
        rid, org, sid, json.dumps({"summary": "Draft feedback"}),
    )
    app.dependency_overrides[_get_student_profile] = lambda: {"uid": "tester", "org_id": org, "role": "student"}
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            hidden = await client.get(f"/api/student/submissions/{sid}/pdf")
            assert hidden.status_code == 404
            await owner.execute("UPDATE feedback_reports SET published_at=now() WHERE id=$1", rid)
            shown = await client.get(f"/api/student/submissions/{sid}/pdf")
            assert shown.status_code == 200, shown.text[:200]
            assert shown.content.startswith(b"%PDF")
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pro_activation_works_under_row_level_security(db):
    owner, org = db
    from app.api.admin_routes import grant_pro, revoke_pro
    from app.api.auth_routes import RedeemCodeBody, auth_redeem_code
    from app.services.stripe_service import stripe_service
    await _make_user(owner, org, "faculty-a")
    await _make_user(owner, org, "faculty-b")
    await _make_user(owner, org, "admin-1", role="admin", faculty="none")

    await stripe_service.sandbox_activate("faculty-a", "pro")
    assert await owner.fetchval("SELECT pro_status FROM users WHERE uid='faculty-a'") == "active"

    await auth_redeem_code(RedeemCodeBody(code="testingphase"), "faculty-b")
    assert await owner.fetchval("SELECT pro_status FROM users WHERE uid='faculty-b'") == "active"

    admin = {"uid": "admin-1", "org_id": org, "role": "admin"}
    await revoke_pro("faculty-b", admin)
    assert await owner.fetchval("SELECT pro_status FROM users WHERE uid='faculty-b'") == "inactive"
    await grant_pro("faculty-b", admin)
    assert await owner.fetchval("SELECT pro_status FROM users WHERE uid='faculty-b'") == "active"
    with pytest.raises(HTTPException) as denied:
        await grant_pro("tester", admin)  # a student
    assert denied.value.status_code == 409


@pytest.mark.asyncio
async def test_routes_enforce_faculty_approval_and_pro(db, monkeypatch):
    owner, org = db
    from app.main import app
    from app.api import instructor_routes
    await _make_user(owner, org, "pending-1", faculty="pending")
    await _make_user(owner, org, "faculty-1")
    await _make_user(owner, org, "pro-1", pro="active")
    current = {}
    app.dependency_overrides[instructor_routes._get_verified_uid] = lambda: current["uid"]
    monkeypatch.setattr(instructor_routes, "_generate_default_rubric", AsyncMock(return_value="Accuracy: 10"))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            current["uid"] = "pending-1"
            assert (await client.get("/api/instructor/subjects")).status_code == 403

            for uid, pro in (("faculty-1", False), ("pro-1", True)):
                current["uid"] = uid
                subject = (await client.post("/api/instructor/subjects", json={"title": f"Course {uid}"})).json()["subject"]["id"]
                created = await client.post(
                    f"/api/instructor/subjects/{subject}/assignments",
                    json={"title": "Essay", "rubric": "Accuracy: 10", "internal_similarity_enabled": True},
                )
                assert created.status_code == 201, created.text
                assert created.json()["internal_similarity_enabled"] is pro
                stored = await owner.fetchval("SELECT internal_similarity_enabled FROM assignments WHERE id=$1", uuid.UUID(created.json()["id"]))
                assert stored is pro
                batch = await client.post(
                    "/api/instructor/batch",
                    data={"assignment_id": created.json()["id"], "subject_id": subject},
                    files={"file": ("class.zip", b"not-a-zip", "application/zip")},
                )
                # Non-Pro is refused before the upload is read; Pro reaches archive validation.
                assert (batch.status_code == 403) is (not pro), batch.text
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_similarity_job_skips_assignments_of_non_pro_owner(db):
    owner, org = db
    from app.services.internal_similarity import refresh_internal_similarity
    await _make_user(owner, org, "faculty-2")
    subject, assignment = uuid.uuid4(), uuid.uuid4()
    await owner.execute("INSERT INTO subjects(id,org_id,instructor_id,title) VALUES ($1,$2,'faculty-2','Course')", subject, org)
    # Simulates an assignment saved before enforcement, or a plan that has since lapsed.
    await owner.execute("INSERT INTO assignments(id,org_id,subject_id,title,internal_similarity_enabled) VALUES ($1,$2,$3,'A',true)", assignment, org, subject)
    for _ in range(2):
        await owner.execute(
            "INSERT INTO submissions(id,org_id,assignment_id,subject_id,type,mode,status,input_text) VALUES ($1,$2,$3,$4,'text','single','graded','Identical answer text about density')",
            uuid.uuid4(), org, assignment, subject,
        )
    await refresh_internal_similarity(str(org), str(assignment))
    assert await owner.fetchval("SELECT count(*) FROM plagiarism_reports") == 0
    await owner.execute("UPDATE users SET pro_status='active' WHERE uid='faculty-2'")
    await refresh_internal_similarity(str(org), str(assignment))
    assert await owner.fetchval("SELECT count(*) FROM plagiarism_reports") == 2

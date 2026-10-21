"""Admin role updates must be authorized and persist across login sync."""
from contextlib import asynccontextmanager

import httpx
import pytest
from fastapi import HTTPException

from app.api import admin_routes
from app.config import settings
from app.main import app
from app.api.auth_routes import _get_verified_claims
from test_document_demo import db  # noqa: F401


class FakeConn:
    def __init__(self, row):
        self.row = row
        self.executed = []

    async def fetchrow(self, sql, *args):
        self.executed.append((sql, args))
        return self.row

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"


def fake_conn(conn):
    @asynccontextmanager
    async def _get_conn(org_id=None):
        yield conn
    return _get_conn


@pytest.mark.asyncio
async def test_revoke_updates_role_and_faculty_approval(monkeypatch):
    conn = FakeConn({"uid": "faculty", "role": "instructor", "faculty_status": "approved"})
    monkeypatch.setattr(admin_routes, "get_conn", fake_conn(conn))
    response = await admin_routes.change_instructor_role(
        "faculty", admin_routes.InstructorRolePayload(role="student"),
        {"uid": "admin", "org_id": "00000000-0000-0000-0000-000000000001"},
    )
    assert response["role"] == "student"
    update = [(query, args) for query, args in conn.executed if "UPDATE users SET role" in query]
    assert len(update) == 1
    assert update[0][1][0:2] == ("student", "rejected")
    assert any("REVOKE_INSTRUCTOR" in args for _, args in conn.executed)


@pytest.mark.asyncio
async def test_admin_accounts_cannot_be_revoked(monkeypatch):
    conn = FakeConn({"uid": "another-admin", "role": "admin", "faculty_status": "approved"})
    monkeypatch.setattr(admin_routes, "get_conn", fake_conn(conn))
    with pytest.raises(HTTPException) as error:
        await admin_routes.change_instructor_role(
            "another-admin", admin_routes.InstructorRolePayload(role="student"),
            {"uid": "admin", "org_id": "00000000-0000-0000-0000-000000000001"},
        )
    assert error.value.status_code == 403
    assert not any("UPDATE users" in query for query, _ in conn.executed)


@pytest.mark.asyncio
async def test_revoked_demo_instructor_cannot_be_restored_by_login(db, monkeypatch):
    owner, org = db
    from app.api.auth_routes import sync_user
    admin_uid = "role-test-admin"
    await owner.execute(
        "INSERT INTO users(uid,org_id,email,role) VALUES ($1,$2,$3,'admin')",
        admin_uid, org, "role-test-admin@example.invalid",
    )
    await owner.execute(
        "UPDATE users SET role='instructor',faculty_status='approved' WHERE uid='tester'"
    )
    monkeypatch.setattr(settings, "DEMO_INSTRUCTOR_EMAILS", "tester@example.invalid")
    app.dependency_overrides[admin_routes._get_admin] = lambda: {"uid": admin_uid, "org_id": org, "role": "admin"}
    app.dependency_overrides[_get_verified_claims] = lambda: {
        "uid": "tester", "email": "tester@example.invalid"
    }
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            revoked = await client.patch("/api/admin/users/tester/role", json={"role": "student"})
            assert revoked.status_code == 200, revoked.text[:200]
            assert revoked.json()["role"] == "student"
            synced = await client.post("/api/auth/sync-user", json={})
            assert synced.status_code == 200, synced.text[:200]
            assert synced.json()["user"]["role"] == "student"
            assert synced.json()["user"]["faculty_status"] == "rejected"
            restored = await client.patch("/api/admin/users/tester/role", json={"role": "instructor"})
            assert restored.status_code == 200, restored.text[:200]
            assert restored.json()["role"] == "instructor"
            synced_again = await client.post("/api/auth/sync-user", json={})
            assert synced_again.json()["user"]["faculty_status"] == "approved"
            assert synced_again.json()["user"]["role"] == "instructor"
    finally:
        app.dependency_overrides.pop(admin_routes._get_admin, None)
        app.dependency_overrides.pop(_get_verified_claims, None)

"""Instructor tools require faculty approval, without a subscription gate."""
from contextlib import asynccontextmanager

import pytest
from fastapi import HTTPException

from app.api import instructor_routes


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,faculty_status,allowed",
    [
        ("student", "none", False),
        ("instructor", "pending", False),
        ("instructor", "approved", True),
        ("admin", "none", True),
    ],
)
async def test_instructor_access_requires_approval_not_pro(monkeypatch, role, faculty_status, allowed):
    class FakeConn:
        async def fetchval(self, *args):
            return "00000000-0000-0000-0000-000000000001"

        async def fetchrow(self, *args):
            return {
                "uid": "uid",
                "org_id": "00000000-0000-0000-0000-000000000001",
                "role": role,
                "faculty_status": faculty_status,
                "pro_status": "inactive",
            }

    @asynccontextmanager
    async def fake_get_conn(org_id=None):
        yield FakeConn()

    monkeypatch.setattr(instructor_routes, "get_conn", fake_get_conn)
    if allowed:
        assert (await instructor_routes._get_instructor("uid"))["role"] == role
    else:
        with pytest.raises(HTTPException) as exc:
            await instructor_routes._get_instructor("uid")
        assert exc.value.status_code == 403

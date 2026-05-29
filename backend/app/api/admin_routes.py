"""
GradeWise v3 — admin routes (Postgres-backed).

GET  /api/admin/faculty-applications           — list pending
POST /api/admin/faculty-applications/{id}/approve
POST /api/admin/faculty-applications/{id}/reject
POST /api/admin/users/{uid}/grant-pro
POST /api/admin/users/{uid}/revoke-pro
GET  /api/admin/warnings
POST /api/admin/warnings/{id}/dismiss
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.auth.firebase import verify_id_token
from app.db.postgres import get_conn

logger = logging.getLogger(__name__)
router = APIRouter()


# ---- Auth dependency --------------------------------------------------------

async def _get_verified_uid(authorization: Annotated[str, Header()]) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        return verify_id_token(token)["uid"]
    except Exception as e:
        raise HTTPException(401, str(e)) from e


async def _get_admin(uid: str = Depends(_get_verified_uid)) -> dict:
    async with get_conn() as conn:
        org_id = await conn.fetchval("SELECT get_user_org_id($1)", uid)
    if not org_id:
        raise HTTPException(403, "Admin role required.")
    async with get_conn(str(org_id)) as conn:
        row = await conn.fetchrow(
            "SELECT uid, org_id, role FROM users WHERE uid = $1", uid
        )
    if not row or row["role"] != "admin":
        raise HTTPException(403, "Admin role required.")
    return dict(row)


# ---- Faculty applications ---------------------------------------------------

@router.get("/faculty-applications")
async def list_faculty_applications(admin: dict = Depends(_get_admin)):
    async with get_conn(str(admin["org_id"])) as conn:
        rows = await conn.fetch(
            "SELECT * FROM faculty_applications ORDER BY created_at DESC LIMIT 200"
        )
    return [dict(r) for r in rows]


class RejectionPayload(BaseModel):
    reason: str


@router.post("/faculty-applications/{app_id}/approve")
async def approve_application(app_id: str, admin: dict = Depends(_get_admin)):
    now = datetime.now(timezone.utc)
    org_id = str(admin["org_id"])

    async with get_conn(org_id) as conn:
        app = await conn.fetchrow(
            "SELECT * FROM faculty_applications WHERE id = $1", app_id
        )
        if not app:
            raise HTTPException(404, "Application not found.")

        await conn.execute(
            """
            UPDATE faculty_applications
            SET status = 'approved', reviewed_by = $1, reviewed_at = $2
            WHERE id = $3
            """,
            admin["uid"], now, app_id,
        )
        await conn.execute(
            """
            UPDATE users
            SET role = 'instructor', faculty_status = 'approved', updated_at = $1
            WHERE uid = $2
            """,
            now, app["user_id"],
        )
        await conn.execute(
            """
            INSERT INTO instructor_profiles (uid, org_id, institution, department, designation, created_at, updated_at)
            VALUES ($1, $2::uuid, $3, $4, $5, $6, $6)
            ON CONFLICT (uid) DO UPDATE
              SET institution = EXCLUDED.institution,
                  department = EXCLUDED.department,
                  designation = EXCLUDED.designation,
                  updated_at = EXCLUDED.updated_at
            """,
            app["user_id"], org_id, app["university"], app["department"], app["designation"], now
        )
        await _write_audit(conn, admin["uid"], "APPROVE_FACULTY", app["user_id"])

    return {"status": "approved", "application_id": app_id}


@router.post("/faculty-applications/{app_id}/reject")
async def reject_application(
    app_id: str,
    payload: RejectionPayload,
    admin: dict = Depends(_get_admin),
):
    now = datetime.now(timezone.utc)
    org_id = str(admin["org_id"])

    async with get_conn(org_id) as conn:
        app = await conn.fetchrow(
            "SELECT * FROM faculty_applications WHERE id = $1", app_id
        )
        if not app:
            raise HTTPException(404, "Application not found.")

        await conn.execute(
            """
            UPDATE faculty_applications
            SET status = 'rejected', rejection_reason = $1,
                reviewed_by = $2, reviewed_at = $3
            WHERE id = $4
            """,
            payload.reason, admin["uid"], now, app_id,
        )
        await conn.execute(
            "UPDATE users SET faculty_status = 'rejected', updated_at = $1 WHERE uid = $2",
            now, app["user_id"],
        )
        await _write_audit(conn, admin["uid"], "REJECT_FACULTY", app["user_id"])

    return {"status": "rejected", "application_id": app_id}


# ---- Pro access -------------------------------------------------------------

@router.post("/users/{target_uid}/grant-pro")
async def grant_pro(target_uid: str, admin: dict = Depends(_get_admin)):
    now = datetime.now(timezone.utc)
    async with get_conn() as conn:
        result = await conn.execute(
            "UPDATE users SET pro_status = 'active', updated_at = $1 WHERE uid = $2",
            now, target_uid,
        )
        if result == "UPDATE 0":
            raise HTTPException(404, "User not found.")
        await _write_audit(conn, admin["uid"], "GRANT_PRO", target_uid)
    return {"status": "pro_granted", "user_id": target_uid}


@router.post("/users/{target_uid}/revoke-pro")
async def revoke_pro(target_uid: str, admin: dict = Depends(_get_admin)):
    now = datetime.now(timezone.utc)
    async with get_conn() as conn:
        result = await conn.execute(
            "UPDATE users SET pro_status = 'inactive', updated_at = $1 WHERE uid = $2",
            now, target_uid,
        )
        if result == "UPDATE 0":
            raise HTTPException(404, "User not found.")
        await _write_audit(conn, admin["uid"], "REVOKE_PRO", target_uid)
    return {"status": "pro_revoked", "user_id": target_uid}


# ---- Warnings ---------------------------------------------------------------

@router.get("/warnings")
async def list_warnings(admin: dict = Depends(_get_admin)):
    async with get_conn(str(admin["org_id"])) as conn:
        rows = await conn.fetch(
            "SELECT * FROM warnings WHERE status = 'active' ORDER BY created_at DESC"
        )
    return [dict(r) for r in rows]


@router.post("/warnings/{warning_id}/dismiss")
async def dismiss_warning(warning_id: str, admin: dict = Depends(_get_admin)):
    now = datetime.now(timezone.utc)
    org_id = str(admin["org_id"])

    async with get_conn(org_id) as conn:
        warn = await conn.fetchrow(
            "SELECT * FROM warnings WHERE id = $1", warning_id
        )
        if not warn:
            raise HTTPException(404, "Warning not found.")
        if warn["status"] == "dismissed":
            return {"status": "already_dismissed"}

        await conn.execute(
            "UPDATE warnings SET status = 'dismissed', dismissed_by = $1 WHERE id = $2",
            admin["uid"], warning_id,
        )
        # Decrement user warning count
        await conn.execute(
            """
            UPDATE users
            SET warning_count = GREATEST(0, warning_count - 1),
                blocked_until = CASE WHEN warning_count - 1 < 3 THEN NULL ELSE blocked_until END
            WHERE uid = $1
            """,
            warn["user_id"],
        )
        await _write_audit(conn, admin["uid"], "DISMISS_WARNING", warn["user_id"])

    return {"status": "dismissed", "warning_id": warning_id}


# ---- Audit helper -----------------------------------------------------------

async def _write_audit(conn, actor_uid: str, action: str, target: str):
    await conn.execute(
        """
        INSERT INTO audit_logs (org_id, actor_uid, action, target)
        SELECT org_id, $1, $2, $3 FROM users WHERE uid = $1
        """,
        actor_uid, action, target,
    )

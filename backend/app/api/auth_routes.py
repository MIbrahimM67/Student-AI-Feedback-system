"""
GradeWise v3 — auth routes.

POST /api/auth/sync-user   — called by the frontend after Google Sign-In.
                             Creates or updates the user row in Postgres.
                             Returns the user's full profile (including role).
POST /api/auth/select-role — first-time role selection. Writes to Postgres.
GET  /api/auth/me          — return current user profile from Postgres.

Role is stored in the Postgres `users` table — never in localStorage.
The frontend reads it from here on every session restore.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header

from app.auth.firebase import verify_id_token
from app.db.postgres import get_conn

logger = logging.getLogger(__name__)
router = APIRouter()

DEV_ORG_ID = "00000000-0000-0000-0000-000000000001"  # seeded in init.sql


async def _get_verified_uid(authorization: Annotated[str, Header()]) -> str:
    """Dependency: verify Firebase token, return uid."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        claims = verify_id_token(token)
        return claims["uid"]
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}") from e


async def _get_user_row(uid: str, org_id: str) -> dict | None:
    async with get_conn(org_id) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE uid = $1", uid
        )
    return dict(row) if row else None


from pydantic import BaseModel

class SyncUserRequest(BaseModel):
    email: str = ""
    displayName: str = ""
    photoURL: str = ""

@router.post("/sync-user")
async def sync_user(
    body: SyncUserRequest,
    uid: str = Depends(_get_verified_uid),
):
    """
    Called by the frontend immediately after Google Sign-In.
    Creates the user if new (role = '', triggers onboarding).
    Returns the full user profile so the frontend knows the role immediately.
    """
    email = body.email
    display_name = body.displayName
    photo_url = body.photoURL
    now = datetime.now(timezone.utc)

    # Determine org_id (single-org for MVP — each user is their own org on first login)
    # In a multi-tenant build, look up the org by email domain or invite token.
    async with get_conn() as conn:
        # Check if user exists (bypass RLS using the SECURITY DEFINER helper function)
        existing = await conn.fetchrow("SELECT get_user_org_id($1) AS org_id", uid)
        org_id = str(existing["org_id"]) if existing and existing["org_id"] else DEV_ORG_ID

    async with get_conn(org_id) as conn:
        await conn.execute(
            """
            INSERT INTO users (uid, org_id, email, display_name, photo_url, role,
                               faculty_status, pro_status, warning_count, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, 'student', 'none', 'inactive', 0, $6, $6)
            ON CONFLICT (uid) DO UPDATE
              SET display_name = EXCLUDED.display_name,
                  photo_url    = EXCLUDED.photo_url,
                  updated_at   = EXCLUDED.updated_at
            """,
            uid, org_id, email, display_name, photo_url, now,
        )
        row = await conn.fetchrow("SELECT * FROM users WHERE uid = $1", uid)

    response_user = dict(row)
    if existing is None:
        # For completely new users, trick the frontend into showing the Role Selection screen
        # even though they are safely defaulted to 'student' in the database.
        response_user["role"] = ""

    return {"user": response_user}


class SelectRoleRequest(BaseModel):
    role: str = ""

@router.post("/select-role")
async def select_role(
    body: SelectRoleRequest,
    uid: str = Depends(_get_verified_uid),
):
    """
    First-time role selection. Writes the role to Postgres — not localStorage.
    Only allowed to set 'student' or 'instructor' (admin is granted by admin only).
    """
    role = body.role
    if role not in ("student", "instructor"):
        raise HTTPException(400, "role must be 'student' or 'instructor'")

    now = datetime.now(timezone.utc)

    async with get_conn() as conn:
        existing = await conn.fetchrow("SELECT org_id FROM users WHERE uid = $1", uid)
        if not existing:
            raise HTTPException(404, "User not found. Call /sync-user first.")
        org_id = str(existing["org_id"])

    async with get_conn(org_id) as conn:
        await conn.execute(
            "UPDATE users SET role = $1, updated_at = $2 WHERE uid = $3",
            role, now, uid,
        )
        row = await conn.fetchrow("SELECT * FROM users WHERE uid = $1", uid)

    return {"user": dict(row)}


@router.get("/me")
async def get_me(uid: str = Depends(_get_verified_uid)):
    """Return the current user's Postgres profile."""
    async with get_conn() as conn:
        row = await conn.fetchrow("SELECT org_id FROM users WHERE uid = $1", uid)
        if not row:
            raise HTTPException(404, "User not found.")
        org_id = str(row["org_id"])

    async with get_conn(org_id) as conn:
        row = await conn.fetchrow("SELECT * FROM users WHERE uid = $1", uid)

    return {"user": dict(row)}

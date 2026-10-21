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
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
import asyncpg

from app.auth.firebase import DemoAccessDenied, grant_beta_access, verify_firebase_identity, verify_id_token
from app.config import settings
from app.db.postgres import get_conn

logger = logging.getLogger(__name__)
router = APIRouter()

DEV_ORG_ID = "00000000-0000-0000-0000-000000000001"  # seeded in init.sql


async def _get_verified_claims(
    authorization: Annotated[str, Header()],
) -> dict:
    """Dependency: verify a Firebase token and return its trusted claims."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    token = authorization.removeprefix("Bearer ")
    try:
        return verify_id_token(token)
    except DemoAccessDenied as e:
        raise HTTPException(403, str(e)) from e
    except Exception as e:
        raise HTTPException(401, f"Invalid token: {e}") from e


async def _get_verified_uid(authorization: Annotated[str, Header()]) -> str:
    """Dependency: verify Firebase token, return uid."""
    claims = await _get_verified_claims(authorization)
    return claims["uid"]


class BetaAccessRequest(BaseModel):
    code: str


@router.post("/beta-access")
async def redeem_beta_access(
    body: BetaAccessRequest,
    authorization: Annotated[str, Header()],
):
    """Grant a verified Google account access after validating the server secret."""
    if not settings.DOCUMENT_DEMO:
        raise HTTPException(404, "Beta access is unavailable.")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    try:
        claims = verify_firebase_identity(authorization.removeprefix("Bearer "))
    except ValueError as e:
        raise HTTPException(401, "Invalid Firebase token") from e
    if not claims.get("uid") or not claims.get("email") or claims.get("email_verified") is not True:
        raise HTTPException(403, "A verified Google email is required.")
    if not settings.BETA_ACCESS_CODE:
        raise HTTPException(503, "Beta access is not configured.")
    if not secrets.compare_digest(body.code, settings.BETA_ACCESS_CODE):
        raise HTTPException(403, "Invalid beta access code.")
    try:
        grant_beta_access(claims["uid"])
    except Exception as e:
        logger.exception("Unable to grant beta access to verified account.")
        raise HTTPException(503, "Unable to activate beta access. Please try again.") from e
    return {"granted": True}


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
    claims: dict = Depends(_get_verified_claims),
):
    """
    Called by the frontend immediately after Google Sign-In.
    Creates the user if new and applies any verified demo invitation.
    Returns the full user profile so the frontend knows the role immediately.
    """
    uid = claims["uid"]
    email = str(claims.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(400, "The signed-in Google account did not provide an email address.")

    display_name = body.displayName or str(claims.get("name") or "")
    photo_url = body.photoURL or str(claims.get("picture") or "")
    now = datetime.now(timezone.utc)

    instructor_emails = {
        value.strip().lower()
        for value in settings.DEMO_INSTRUCTOR_EMAILS.split(",")
        if value.strip()
    }
    invited_instructor = settings.DOCUMENT_DEMO and email in instructor_emails
    initial_role = "instructor" if invited_instructor else "student"
    initial_faculty_status = "approved" if invited_instructor else "none"

    # Determine org_id (single-org for MVP).
    async with get_conn() as conn:
        existing = await conn.fetchrow("SELECT get_user_org_id($1) AS org_id", uid)
        org_id = str(existing["org_id"]) if existing and existing["org_id"] else DEV_ORG_ID

    async with get_conn(org_id) as conn:
        try:
            await conn.execute(
                """
                INSERT INTO users (uid, org_id, email, display_name, photo_url, role,
                                   faculty_status, pro_status, warning_count, created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'inactive', 0, $8, $8)
                ON CONFLICT (uid) DO UPDATE
                  SET email        = EXCLUDED.email,
                      display_name = EXCLUDED.display_name,
                      photo_url    = EXCLUDED.photo_url,
                      role         = CASE
                                       WHEN users.role = 'admin' THEN users.role
                                       -- An admin revocation overrides demo email invitations.
                                       WHEN users.faculty_status = 'rejected' THEN 'student'
                                       WHEN EXCLUDED.role = 'instructor' THEN 'instructor'
                                       ELSE users.role
                                     END,
                      faculty_status = CASE
                                         WHEN users.faculty_status = 'rejected' THEN 'rejected'
                                         WHEN EXCLUDED.faculty_status = 'approved' THEN 'approved'
                                         ELSE users.faculty_status
                                       END,
                      updated_at   = EXCLUDED.updated_at
                """,
                uid, org_id, email, display_name, photo_url,
                initial_role, initial_faculty_status, now,
            )
        except asyncpg.exceptions.UniqueViolationError:
            # The user recreated their Firebase account (new UID) but with the same email.
            logger.warning("Email %s already exists with a different UID. Replacing orphaned row.", email)
            await conn.execute("DELETE FROM users WHERE email = $1", email)
            await conn.execute(
                """
                INSERT INTO users (uid, org_id, email, display_name, photo_url, role,
                                   faculty_status, pro_status, warning_count, created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, 'inactive', 0, $8, $8)
                """,
                uid, org_id, email, display_name, photo_url,
                initial_role, initial_faculty_status, now,
            )

        if invited_instructor:
            await conn.execute(
                """
                INSERT INTO instructor_profiles (uid, org_id, created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $3)
                ON CONFLICT (uid) DO UPDATE
                  SET org_id = EXCLUDED.org_id,
                      updated_at = EXCLUDED.updated_at
                """,
                uid, org_id, now,
            )

        row = await conn.fetchrow("SELECT * FROM users WHERE uid = $1", uid)

    response_user = dict(row)
    if (not existing or existing["org_id"] is None) and not invited_instructor:
        response_user["role"] = ""

    return {"user": response_user}


from typing import Optional

class SelectRoleRequest(BaseModel):
    role: str = ""
    display_name: Optional[str] = None
    institution: Optional[str] = None
    department: Optional[str] = None

@router.post("/select-role")
async def select_role(
    body: SelectRoleRequest,
    uid: str = Depends(_get_verified_uid),
):
    """
    First-time role selection / profile onboarding.
    Only allowed to set 'student' or 'instructor' (admin is granted by admin only).
    """
    role = body.role
    if role not in ("student", "instructor"):
        raise HTTPException(400, "role must be 'student' or 'instructor'")

    now = datetime.now(timezone.utc)

    async with get_conn() as conn:
        org_id_val = await conn.fetchval("SELECT get_user_org_id($1)", uid)
        if not org_id_val:
            raise HTTPException(404, "User not found. Call /sync-user first.")
        org_id = str(org_id_val)


    async with get_conn(org_id) as conn:
        # A role picker must not override an explicit admin denial.
        if role == "instructor":
            current_status = await conn.fetchval(
                "SELECT faculty_status FROM users WHERE uid = $1", uid
            )
            if current_status == "rejected":
                raise HTTPException(403, "Instructor access was denied or revoked by an administrator.")
        # Update users table
        if body.display_name:
            await conn.execute(
                "UPDATE users SET role = $1, display_name = $2, updated_at = $3 WHERE uid = $4",
                role, body.display_name, now, uid,
            )
        else:
            await conn.execute(
                "UPDATE users SET role = $1, updated_at = $2 WHERE uid = $3",
                role, now, uid,
            )
            
        # Create profile record based on role
        if role == "instructor":
            await conn.execute(
                """
                INSERT INTO instructor_profiles (uid, org_id, institution, department, created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $5)
                ON CONFLICT (uid) DO UPDATE
                  SET institution = EXCLUDED.institution,
                      department = EXCLUDED.department,
                      updated_at = EXCLUDED.updated_at
                """,
                uid, org_id, body.institution, body.department, now
            )
        elif role == "student":
            await conn.execute(
                """
                INSERT INTO student_profiles (uid, org_id, institution, department, created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $5)
                ON CONFLICT (uid) DO UPDATE
                  SET institution = EXCLUDED.institution,
                      department = EXCLUDED.department,
                      updated_at = EXCLUDED.updated_at
                """,
                uid, org_id, body.institution, body.department, now
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


# ---- Profile GET / PATCH (available to all roles) ---------------------------

class ProfileUpdateRequest(BaseModel):
    display_name: Optional[str] = None
    # Shared
    institution: Optional[str] = None
    department: Optional[str] = None
    # Instructor-only
    designation: Optional[str] = None
    teaching_level: Optional[str] = None
    grading_style: Optional[str] = None


@router.get("/profile")
async def get_profile(uid: str = Depends(_get_verified_uid)):
    """Return user row merged with role-specific profile fields."""
    async with get_conn() as conn:
        org_id_val = await conn.fetchval("SELECT get_user_org_id($1)", uid)
    if not org_id_val:
        raise HTTPException(404, "User not found.")
    org_id = str(org_id_val)

    async with get_conn(org_id) as conn:
        user_row = await conn.fetchrow("SELECT * FROM users WHERE uid = $1", uid)
        if not user_row:
            raise HTTPException(404, "User not found.")

        role = user_row["role"]
        profile_data: dict = {}

        if role == "instructor" or role == "admin":
            p = await conn.fetchrow(
                "SELECT institution, department, designation, teaching_level, grading_style "
                "FROM instructor_profiles WHERE uid = $1", uid
            )
            if p:
                profile_data = dict(p)
        elif role == "student":
            p = await conn.fetchrow(
                "SELECT institution, department FROM student_profiles WHERE uid = $1", uid
            )
            if p:
                profile_data = dict(p)

    result = dict(user_row)
    result.update(profile_data)
    return {"profile": result}


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdateRequest,
    uid: str = Depends(_get_verified_uid),
):
    """Update display_name and/or role-specific profile fields."""
    async with get_conn() as conn:
        org_id_val = await conn.fetchval("SELECT get_user_org_id($1)", uid)
    if not org_id_val:
        raise HTTPException(404, "User not found.")
    org_id = str(org_id_val)

    now = datetime.now(timezone.utc)

    async with get_conn(org_id) as conn:
        user_row = await conn.fetchrow("SELECT role FROM users WHERE uid = $1", uid)
        if not user_row:
            raise HTTPException(404, "User not found.")
        role = user_row["role"]

        # Always update display_name if provided
        if body.display_name is not None:
            await conn.execute(
                "UPDATE users SET display_name = $1, updated_at = $2 WHERE uid = $3",
                body.display_name.strip() or None, now, uid,
            )

        if role in ("instructor", "admin"):
            await conn.execute(
                """
                INSERT INTO instructor_profiles
                  (uid, org_id, institution, department, designation, teaching_level, grading_style, created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $6, $7, $8, $8)
                ON CONFLICT (uid) DO UPDATE
                  SET institution    = COALESCE(EXCLUDED.institution,    instructor_profiles.institution),
                      department     = COALESCE(EXCLUDED.department,     instructor_profiles.department),
                      designation    = COALESCE(EXCLUDED.designation,    instructor_profiles.designation),
                      teaching_level = COALESCE(EXCLUDED.teaching_level, instructor_profiles.teaching_level),
                      grading_style  = COALESCE(EXCLUDED.grading_style,  instructor_profiles.grading_style),
                      updated_at     = EXCLUDED.updated_at
                """,
                uid, org_id,
                body.institution, body.department,
                body.designation, body.teaching_level,
                body.grading_style if body.grading_style in ("strict", "lenient", "balanced", None) else None,
                now,
            )
        elif role == "student":
            await conn.execute(
                """
                INSERT INTO student_profiles (uid, org_id, institution, department, created_at, updated_at)
                VALUES ($1, $2::uuid, $3, $4, $5, $5)
                ON CONFLICT (uid) DO UPDATE
                  SET institution = COALESCE(EXCLUDED.institution, student_profiles.institution),
                      department  = COALESCE(EXCLUDED.department,  student_profiles.department),
                      updated_at  = EXCLUDED.updated_at
                """,
                uid, org_id, body.institution, body.department, now,
            )

        # Re-fetch merged profile to return
        user_row = await conn.fetchrow("SELECT * FROM users WHERE uid = $1", uid)
        result = dict(user_row)

        if role in ("instructor", "admin"):
            p = await conn.fetchrow(
                "SELECT institution, department, designation, teaching_level, grading_style "
                "FROM instructor_profiles WHERE uid = $1", uid
            )
            if p:
                result.update(dict(p))
        elif role == "student":
            p = await conn.fetchrow(
                "SELECT institution, department FROM student_profiles WHERE uid = $1", uid
            )
            if p:
                result.update(dict(p))

    return {"profile": result, "message": "Profile updated successfully."}


class RedeemCodeBody(BaseModel):
    code: str
    plan_id: str = "pro"


@router.post("/redeem-code")
async def auth_redeem_code(
    body: RedeemCodeBody,
    uid: Annotated[str, Depends(_get_verified_uid)],
):
    code = body.code.strip().lower()
    if code != "testingphase":
        raise HTTPException(400, "Invalid or expired promo code.")

    now = datetime.now(timezone.utc)
    async with get_conn() as conn:
        org_id_val = await conn.fetchval("SELECT get_user_org_id($1)", uid)
    if not org_id_val:
        raise HTTPException(404, "User not found.")
    # Row-level security only exposes the user's row inside its tenant context.
    async with get_conn(str(org_id_val)) as conn:
        user_row = await conn.fetchrow("SELECT role, faculty_status FROM users WHERE uid = $1", uid)
        if not user_row:
            raise HTTPException(404, "User not found.")
        if user_row["role"] != "admin" and user_row["faculty_status"] != "approved":
            raise HTTPException(403, "Only approved faculty members can activate Pro.")

        await conn.execute(
            """
            UPDATE users SET
              pro_status = 'active',
              plan = 'pro',
              subscription_status = 'active',
              updated_at = $1
            WHERE uid = $2
            """,
            now, uid
        )
    return {
        "status": "success",
        "message": "🎉 Promo code applied! Pro status is now active.",
        "pro_status": "active"
    }



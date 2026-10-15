"""Faculty verification and Pro plan checks shared by routes and background jobs.

Rules:
  * Instructor features need role 'admin', or role 'instructor' with an
    approved faculty application.
  * Batch upload, similarity checks and exports additionally need an active
    Pro plan. Administrators are treated as entitled.
"""
from __future__ import annotations

from typing import Any, Mapping

FACULTY_REQUIRED_DETAIL = (
    "Instructor tools are available after an administrator approves your faculty application."
)
PRO_REQUIRED_DETAIL = (
    "An active Pro plan is required for batch uploads, similarity checks and exports."
)


def is_verified_faculty(user: Mapping[str, Any]) -> bool:
    role = user.get("role")
    if role == "admin":
        return True
    return role == "instructor" and user.get("faculty_status") == "approved"


def has_active_pro(user: Mapping[str, Any]) -> bool:
    if not is_verified_faculty(user):
        return False
    return user.get("role") == "admin" or user.get("pro_status") == "active"


async def assignment_owner_has_pro(conn, assignment_id) -> bool:
    """True when the instructor who owns the assignment's subject is entitled to Pro features."""
    if not assignment_id:
        return False
    row = await conn.fetchrow(
        """
        SELECT u.role, u.faculty_status, u.pro_status
        FROM assignments a
        JOIN subjects s ON s.id = a.subject_id
        JOIN users u ON u.uid = s.instructor_id
        WHERE a.id = $1
        """,
        assignment_id,
    )
    return bool(row) and has_active_pro(dict(row))

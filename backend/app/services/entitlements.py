"""Faculty verification for instructor workflows and optional billing plan state."""
from __future__ import annotations

from typing import Any, Mapping

FACULTY_REQUIRED_DETAIL = (
    "Instructor tools are available after an administrator approves your faculty application."
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


async def assignment_owner_is_verified(conn, assignment_id) -> bool:
    """Check the owning instructor before running assignment similarity jobs."""
    if not assignment_id:
        return False
    row = await conn.fetchrow(
        """
        SELECT u.role, u.faculty_status
        FROM assignments a
        JOIN subjects s ON s.id = a.subject_id
        JOIN users u ON u.uid = s.instructor_id
        WHERE a.id = $1
        """,
        assignment_id,
    )
    return bool(row) and is_verified_faculty(dict(row))

"""
GradeWise v3 — warning service (Postgres-backed).

Scans student submissions for policy violations and records them
in the `warnings` table. Increments user warning_count and applies
a 7-day block when count >= 3.

No Firestore. No mock data.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Tuple

from app.db.postgres import get_conn

logger = logging.getLogger(__name__)

SENSITIVE_TERMS = [
    "cheat sheet", "leaked exam", "exam leak", "confidential key",
    "proprietary source", "hack database", "bypass authentication",
    "answer key stolen", "model answer leak",
]


class WarningService:

    async def scan_and_enforce(
        self,
        org_id: str,
        user_id: str,
        submission_id: str,
        text: str,
    ) -> Tuple[bool, str]:
        """
        Scan submission text for policy violations.
        Returns (is_violated, reason_message).
        """
        text_lower = text.lower()
        matched = [t for t in SENSITIVE_TERMS if t in text_lower]

        if not matched:
            return False, ""

        reason = f"Sensitive content detected: {', '.join(matched)}"
        severity = "high" if len(matched) > 1 else "medium"
        logger.warning("Policy violation for user=%s submission=%s: %s", user_id, submission_id, reason)

        warning_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with get_conn(org_id) as conn:
            # 1. Insert warning record
            await conn.execute(
                """
                INSERT INTO warnings
                  (id, org_id, user_id, submission_id, reason, severity, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
                """,
                warning_id, org_id, user_id, submission_id, reason, severity, now,
            )

            # 2. Increment warning count; block if >= 3
            row = await conn.fetchrow(
                "SELECT warning_count FROM users WHERE uid = $1", user_id
            )
            if row:
                new_count = (row["warning_count"] or 0) + 1
                blocked_until = None
                if new_count >= 3:
                    blocked_until = now + timedelta(days=7)
                    logger.warning(
                        "User %s blocked until %s (warning_count=%d)",
                        user_id, blocked_until.isoformat(), new_count,
                    )
                await conn.execute(
                    """
                    UPDATE users
                    SET warning_count = $1,
                        blocked_until = $2,
                        updated_at = $3
                    WHERE uid = $4
                    """,
                    new_count, blocked_until, now, user_id,
                )

            # 3. Audit log
            await conn.execute(
                """
                INSERT INTO audit_logs (org_id, actor_uid, action, target, meta, created_at)
                VALUES ($1, 'SYSTEM', 'POLICY_VIOLATION', $2, $3, $4)
                """,
                org_id, user_id,
                {"submission_id": submission_id, "reason": reason},
                now,
            )

        return True, reason


# Global instance
warning_service = WarningService()

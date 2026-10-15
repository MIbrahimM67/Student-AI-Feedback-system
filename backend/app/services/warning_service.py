"""
GradeWise v3 — warning service (Postgres-backed).

Scans student submissions for policy violations and records them
in the `warnings` table. Increments user warning_count and applies
a 7-day block when count >= 3.

No Firestore. No mock data.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from app.db.postgres import get_conn

logger = logging.getLogger(__name__)

SENSITIVE_TERMS = [
    "cheat sheet", "leaked exam", "exam leak", "confidential key",
    "proprietary source", "hack database", "bypass authentication",
    "answer key stolen", "model answer leak",
]


def find_policy_terms(text: str) -> list[str]:
    text_lower = (text or "").lower()
    return [t for t in SENSITIVE_TERMS if t in text_lower]


class WarningService:

    async def scan_and_enforce(
        self,
        org_id: str,
        user_id: Optional[str],
        submission_id: str,
        text: str,
    ) -> Tuple[bool, str]:
        """
        Scan submission text for policy violations.
        Returns (is_violated, reason_message).

        user_id is None for instructor uploads (single-upload or batch). Those
        submissions are still stopped and audited, but no student account
        receives a warning or a block.
        """
        matched = find_policy_terms(text)

        if not matched:
            return False, ""

        reason = f"Sensitive content detected: {', '.join(matched)}"
        severity = "high" if len(matched) > 1 else "medium"
        logger.warning("Policy violation for user=%s submission=%s: %s", user_id, submission_id, reason)

        warning_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        async with get_conn(org_id) as conn:
            if user_id is None:
                await conn.execute(
                    """
                    INSERT INTO audit_logs (org_id, actor_uid, action, target, meta, created_at)
                    VALUES ($1, NULL, 'POLICY_VIOLATION', $2, $3, $4)
                    """,
                    org_id, submission_id,
                    json.dumps({"submission_id": submission_id, "reason": reason, "account": None}),
                    now,
                )
                return True, reason

            # 1. Insert warning record
            await conn.execute(
                """
                INSERT INTO warnings
                  (id, org_id, user_id, submission_id, reason, severity, status, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, 'active', $7)
                """,
                warning_id, org_id, user_id, submission_id, reason, severity, now,
            )

            # 2. Increment warning count atomically; block for 7 days at 3 or more
            row = await conn.fetchrow(
                """
                UPDATE users
                SET warning_count = warning_count + 1,
                    blocked_until = CASE WHEN warning_count + 1 >= 3 THEN $1 ELSE blocked_until END,
                    updated_at = $2
                WHERE uid = $3
                RETURNING warning_count, blocked_until
                """,
                now + timedelta(days=7), now, user_id,
            )
            if row and row["warning_count"] >= 3:
                logger.warning(
                    "User %s blocked until %s (warning_count=%d)",
                    user_id, row["blocked_until"].isoformat(), row["warning_count"],
                )

            # 3. Audit log (system entry: no acting user; meta is JSONB text)
            await conn.execute(
                """
                INSERT INTO audit_logs (org_id, actor_uid, action, target, meta, created_at)
                VALUES ($1, NULL, 'POLICY_VIOLATION', $2, $3, $4)
                """,
                org_id, user_id,
                json.dumps({"submission_id": submission_id, "reason": reason}),
                now,
            )

        return True, reason


# Global instance
warning_service = WarningService()

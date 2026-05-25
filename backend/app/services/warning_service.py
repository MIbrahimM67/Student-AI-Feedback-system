import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple
from backend.app.firebase import db

logger = logging.getLogger("warning_service")

class WarningService:
    def __init__(self):
        # Sensitive terms triggering academic policy warnings
        self.sensitive_terms = [
            "cheat sheet", "leaked exam", "exam leak", "confidential key",
            "proprietary source", "hack database", "bypass authentication"
        ]

    async def scan_and_enforce(self, user_id: str, submission_id: str, text: str) -> Tuple[bool, str]:
        """
        Scans a student's submission text for policy violations.
        Returns:
            Tuple containing:
            - is_violated (bool)
            - reason_message (str)
        """
        logger.info(f"Running compliance policy scan on submission {submission_id} for user {user_id}...")
        
        text_lower = text.lower()
        matched_terms = [term for term in self.sensitive_terms if term in text_lower]
        
        if not matched_terms:
            return False, ""
            
        reason = f"Sensitive material detected: code phrase matching '{', '.join(matched_terms)}'"
        logger.warning(f"Compliance violation found for user {user_id}: {reason}")
        
        # 1. Create a document in Firestore 'warnings' collection
        warning_id = f"warn_{submission_id[:8]}"
        warning_data = {
            "id": warning_id,
            "userId": user_id,
            "submissionId": submission_id,
            "reason": reason,
            "severity": "medium" if len(matched_terms) == 1 else "high",
            "status": "active",
            "createdAt": datetime.utcnow().isoformat(),
            "dismissedBy": None
        }
        
        try:
            db.collection("warnings").document(warning_id).set(warning_data)
        except Exception as e:
            logger.error(f"Failed to record warning in Firestore ({e})")
            
        # 2. Update user warning count and block if repeated
        await self._increment_user_warnings_and_block_check(user_id, reason)
        
        # 3. Write an audit log
        self._write_audit_log(user_id, "POLICY_VIOLATION", f"Submission {submission_id} flagged: {reason}")
        
        return True, reason

    async def _increment_user_warnings_and_block_check(self, user_id: str, reason: str):
        try:
            user_ref = db.collection("users").document(user_id)
            user_snap = user_ref.get()
            
            if not user_snap.exists:
                return
                
            user_data = user_snap.to_dict() or {}
            current_warnings = user_data.get("warningCount", 0) + 1
            
            updates = {"warningCount": current_warnings, "updatedAt": datetime.utcnow().isoformat()}
            
            # Policy rules: If warning count exceeds 3, block user for 7 days
            if current_warnings >= 3:
                blocked_until = (datetime.utcnow() + timedelta(days=7)).isoformat()
                updates["blockedUntil"] = blocked_until
                logger.warning(f"User {user_id} has reached {current_warnings} warnings. Applying a 7-day policy block until {blocked_until}.")
                self._write_audit_log("SYSTEM", "USER_BLOCKED", f"User {user_id} blocked automatically for reaching warning quota.")
            
            user_ref.update(updates)
            
        except Exception as e:
            logger.error(f"Failed to update user warning count ({e})")

    def _write_audit_log(self, actor_id: str, action: str, details: str):
        import uuid
        log_id = str(uuid.uuid4())
        log_data = {
            "id": log_id,
            "actorId": actor_id,
            "action": action,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }
        try:
            db.collection("auditLogs").document(log_id).set(log_data)
            logger.info(f"[Audit Log] {action}: {details}")
        except Exception as e:
            logger.error(f"Failed to write audit log ({e})")

# Initialize global instance
warning_service = WarningService()

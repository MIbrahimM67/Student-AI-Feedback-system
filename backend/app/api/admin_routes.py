from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime
from backend.app.firebase import db
from backend.app.utils.security import get_current_user, require_admin

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"])

class RejectionPayload(BaseModel):
    reason: str

@router.get("/faculty-applications")
async def list_faculty_applications(user: Dict[str, Any] = Depends(require_admin)):
    """
    Returns lists of all submitted instructor verification papers.
    """
    try:
        apps = db.collection("facultyApplications").stream()
        results = [doc.to_dict() for doc in apps]
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {e}")

@router.post("/faculty-applications/{id}/approve")
async def approve_faculty_application(id: str, user: Dict[str, Any] = Depends(require_admin)):
    """
    Approves a pending faculty applicant, upgrades their role, and writes audits.
    """
    try:
        app_ref = db.collection("facultyApplications").document(id)
        app_snap = app_ref.get()
        
        if not app_snap.exists:
            raise HTTPException(status_code=404, detail="Application record not found.")
            
        app_data = app_snap.to_dict() or {}
        applicant_uid = app_data.get("userId")
        
        # Update Application
        app_ref.update({
            "status": "approved",
            "reviewedBy": user["uid"],
            "reviewedAt": datetime.utcnow().isoformat()
        })
        
        # Upgrade User settings in db
        db.collection("users").document(applicant_uid).update({
            "role": "instructor",
            "facultyStatus": "approved",
            "updatedAt": datetime.utcnow().isoformat()
        })
        
        # Write Audit Log
        _write_audit_log(user["uid"], "APPROVE_FACULTY", f"Approved instructor verification for UID: {applicant_uid}")
        
        return {"status": "approved", "applicationId": id, "userId": applicant_uid}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Approval action failed: {e}")

@router.post("/faculty-applications/{id}/reject")
async def reject_faculty_application(id: str, payload: RejectionPayload, user: Dict[str, Any] = Depends(require_admin)):
    """
    Rejects a faculty verification application with clear feedback justification.
    """
    try:
        app_ref = db.collection("facultyApplications").document(id)
        app_snap = app_ref.get()
        
        if not app_snap.exists:
            raise HTTPException(status_code=404, detail="Application record not found.")
            
        app_data = app_snap.to_dict() or {}
        applicant_uid = app_data.get("userId")
        
        # Update Application status
        app_ref.update({
            "status": "rejected",
            "rejectionReason": payload.reason,
            "reviewedBy": user["uid"],
            "reviewedAt": datetime.utcnow().isoformat()
        })
        
        # Reset User facultyStatus
        db.collection("users").document(applicant_uid).update({
            "facultyStatus": "rejected",
            "updatedAt": datetime.utcnow().isoformat()
        })
        
        # Write Audit Log
        _write_audit_log(user["uid"], "REJECT_FACULTY", f"Rejected instructor verification for UID: {applicant_uid}. Reason: {payload.reason}")
        
        return {"status": "rejected", "applicationId": id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rejection action failed: {e}")

@router.post("/users/{id}/grant-pro")
async def grant_pro_access(id: str, user: Dict[str, Any] = Depends(require_admin)):
    """
    Grants premium status, unlocking batch grading and similarities.
    """
    try:
        user_ref = db.collection("users").document(id)
        user_snap = user_ref.get()
        
        if not user_snap.exists:
            raise HTTPException(status_code=404, detail="User record not found.")
            
        user_ref.update({
            "proStatus": "active",
            "updatedAt": datetime.utcnow().isoformat()
        })
        
        _write_audit_log(user["uid"], "GRANT_PRO", f"Granted Pro access to UID: {id}")
        return {"status": "pro_granted", "userId": id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to grant Pro access: {e}")

@router.post("/users/{id}/revoke-pro")
async def revoke_pro_access(id: str, user: Dict[str, Any] = Depends(require_admin)):
    """
    Revokes premium access configurations.
    """
    try:
        user_ref = db.collection("users").document(id)
        user_snap = user_ref.get()
        
        if not user_snap.exists:
            raise HTTPException(status_code=404, detail="User record not found.")
            
        user_ref.update({
            "proStatus": "inactive",
            "updatedAt": datetime.utcnow().isoformat()
        })
        
        _write_audit_log(user["uid"], "REVOKE_PRO", f"Revoked Pro access from UID: {id}")
        return {"status": "pro_revoked", "userId": id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to revoke Pro access: {e}")

@router.get("/warnings")
async def list_warnings(user: Dict[str, Any] = Depends(require_admin)):
    """
    Returns details of all active plagiarism or content moderation violations.
    """
    try:
        warns = db.collection("warnings").stream()
        results = [doc.to_dict() for doc in warns]
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch warnings: {e}")

@router.post("/warnings/{id}/dismiss")
async def dismiss_warning(id: str, user: Dict[str, Any] = Depends(require_admin)):
    """
    Dismisses an active compliance warning, decrementing user warning counts.
    """
    try:
        warn_ref = db.collection("warnings").document(id)
        warn_snap = warn_ref.get()
        
        if not warn_snap.exists:
            raise HTTPException(status_code=404, detail="Warning record not found.")
            
        warn_data = warn_snap.to_dict() or {}
        violator_uid = warn_data.get("userId")
        
        if warn_data.get("status") == "dismissed":
            return {"status": "already_dismissed", "warningId": id}
            
        # Update warning status
        warn_ref.update({
            "status": "dismissed",
            "dismissedBy": user["uid"]
        })
        
        # Decrement user warning counts
        user_ref = db.collection("users").document(violator_uid)
        user_snap = user_ref.get()
        if user_snap.exists:
            usr_data = user_snap.to_dict() or {}
            current_warns = max(0, usr_data.get("warningCount", 0) - 1)
            
            updates = {"warningCount": current_warns}
            
            # If warning falls below limit, unblock user
            if current_warns < 3:
                updates["blockedUntil"] = None
                
            user_ref.update(updates)
            
        _write_audit_log(user["uid"], "DISMISS_WARNING", f"Dismissed warning ID: {id} for user UID: {violator_uid}")
        return {"status": "dismissed", "warningId": id, "decrementedWarningCount": current_warns}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to dismiss warning: {e}")

# Helper to write Audit logs
def _write_audit_log(admin_uid: str, action: str, details: str):
    import uuid
    log_id = str(uuid.uuid4())
    log_data = {
        "id": log_id,
        "actorId": admin_uid,
        "action": action,
        "details": details,
        "timestamp": datetime.utcnow().isoformat()
    }
    try:
        db.collection("auditLogs").document(log_id).set(log_data)
    except Exception:
        pass

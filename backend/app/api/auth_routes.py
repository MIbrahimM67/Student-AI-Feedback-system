from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
from backend.app.firebase import db
from backend.app.utils.security import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

class RoleSelectionRequest(BaseModel):
    role: str # 'student' or 'instructor'

class SyncUserRequest(BaseModel):
    email: str
    displayName: str
    photoURL: Optional[str] = None

@router.post("/sync-user")
async def sync_user(payload: SyncUserRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Called upon successful frontend Google OAuth login. Syncs profile details in Firestore.
    """
    uid = user["uid"]
    logger_msg = f"Syncing user login: {uid} | {payload.email}"
    
    try:
        user_ref = db.collection("users").document(uid)
        snapshot = user_ref.get()
        if not snapshot.exists:
            user_data = {
                "uid": uid,
                "email": payload.email,
                "displayName": payload.displayName,
                "photoURL": payload.photoURL,
                "role": "", # Initialized empty to prompt role onboarding select deck
                "facultyStatus": "none",
                "proStatus": "inactive",
                "warningCount": 0,
                "blockedUntil": None,
                "createdAt": datetime.utcnow().isoformat(),
                "updatedAt": datetime.utcnow().isoformat()
            }
            user_ref.set(user_data)
            return {"status": "created", "user": user_data}
        else:
            # Refresh standard display items
            existing_data = snapshot.to_dict() or {}
            existing_data.update({
                "displayName": payload.displayName,
                "photoURL": payload.photoURL,
                "updatedAt": datetime.utcnow().isoformat()
            })
            user_ref.update(existing_data)
            return {"status": "synchronized", "user": existing_data}
            
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database synchronization error: {e}"
        )

@router.get("/me")
async def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Returns full profile settings of the currently authenticated active session.
    """
    return user

@router.post("/select-role")
async def select_role(payload: RoleSelectionRequest, user: Dict[str, Any] = Depends(get_current_user)):
    """
    Permits students and instructors to choose their role on initial sign-up onboarding.
    """
    uid = user["uid"]
    role = payload.role.lower()
    
    if role not in ["student", "instructor"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role selection must be either 'student' or 'instructor'."
        )
        
    try:
        user_ref = db.collection("users").document(uid)
        user_ref.update({
            "role": role,
            "updatedAt": datetime.utcnow().isoformat()
        })
        
        # Read refreshed document
        refreshed = user_ref.get().to_dict()
        return {"status": "role_updated", "user": refreshed}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update user role: {e}"
        )

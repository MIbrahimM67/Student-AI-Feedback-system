from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from datetime import datetime
from typing import Dict, Any
from backend.app.firebase import firebase_auth, db

# Define HTTP Bearer security scheme
security_scheme = HTTPBearer(auto_error=True)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Security(security_scheme)) -> Dict[str, Any]:
    """
    Extracts authorization token, verifies it against Firebase, 
    and returns the fully hydrated user profile document from Firestore.
    """
    token = credentials.credentials
    try:
        # Decodes token via Firebase Auth
        decoded_token = firebase_auth.verify_id_token(token)
        uid = decoded_token["uid"]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_410_GONE if "expired" in str(e).lower() else status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired credentials: {e}"
        )

    # Fetch Firestore profile
    try:
        user_snap = db.collection("users").document(uid).get()
        if not user_snap.exists:
            # Sync / Create a lazy default student profile if not present
            user_data = {
                "uid": uid,
                "email": decoded_token.get("email", "student@academic.edu"),
                "displayName": decoded_token.get("name", "Student User"),
                "role": "student",
                "facultyStatus": "none",
                "proStatus": "inactive",
                "warningCount": 0,
                "blockedUntil": None,
                "createdAt": datetime.utcnow().isoformat(),
                "updatedAt": datetime.utcnow().isoformat()
            }
            db.collection("users").document(uid).set(user_data)
        else:
            user_data = user_snap.to_dict() or {}

        # Enforce check_not_blocked rule
        blocked_until_str = user_data.get("blockedUntil")
        if blocked_until_str:
            try:
                blocked_until = datetime.fromisoformat(blocked_until_str)
                if blocked_until > datetime.utcnow():
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"Access denied. Your account is temporarily blocked for policy violations until {blocked_until_str}."
                    )
            except ValueError:
                pass
                
        return user_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database synchronization error: {e}"
        )

# --- ROLE-BASED ACCESS CONTROL DEPENDENCY GUARDS ---

def require_role(allowed_roles: list[str]):
    def dependency(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = user.get("role", "student")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access restricted. Requires one of these roles: {allowed_roles}. Current role: {user_role}."
            )
        return user
    return dependency

require_student = require_role(["student"])
require_instructor = require_role(["instructor"])
require_admin = require_role(["admin"])

def require_pro(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Guards pro subscription features. Allow admins and active Pro instructors.
    """
    role = user.get("role")
    pro_status = user.get("proStatus", "inactive")
    
    if role == "admin":
        return user
        
    if role == "instructor" and pro_status == "active":
        return user
        
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail="Pro subscription active status is required to access batch operations and similarity checking."
    )

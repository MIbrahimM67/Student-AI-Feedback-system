"""
GradeWise v3 — Firebase Auth verification (Auth + Storage ONLY).

All user data and roles live in Postgres. Firebase is ONLY used for:
  1. Verifying Google Sign-In ID tokens.
  2. Uploading/downloading files from Firebase Storage.

NO Firestore. NO mock clients.
"""
from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger(__name__)

_firebase_auth = None
_storage_bucket = None


class DemoAccessDenied(PermissionError):
    """A verified Firebase account that has not been invited to this demo."""

    def __init__(self, uid: str):
        super().__init__(
            "Beta access required: This workspace is open to beta testers. "
            "Enter your access code to continue."
        )


def _init_firebase():
    global _firebase_auth, _storage_bucket
    if _firebase_auth is not None:
        return

    project_id = os.environ.get("FIREBASE_PROJECT_ID", "")
    client_email = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
    private_key = os.environ.get("FIREBASE_PRIVATE_KEY", "").strip("'").strip('"').replace("\\n", "\n")
    storage_bucket = os.environ.get("FIREBASE_STORAGE_BUCKET", "")

    if not all([project_id, client_email, private_key]):
        logger.warning(
            "Firebase credentials incomplete — token verification will fail. "
            "Set FIREBASE_PROJECT_ID, FIREBASE_CLIENT_EMAIL, FIREBASE_PRIVATE_KEY."
        )
        return

    try:
        import firebase_admin
        from firebase_admin import credentials, auth, storage

        if not firebase_admin._apps:
            cred = credentials.Certificate({
                "type": "service_account",
                "project_id": project_id,
                "private_key_id": os.environ.get("FIREBASE_PRIVATE_KEY_ID", "key"),
                "private_key": private_key,
                "client_email": client_email,
                "client_id": os.environ.get("FIREBASE_CLIENT_ID", ""),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "client_x509_cert_url": (
                    f"https://www.googleapis.com/robot/v1/metadata/x509/"
                    + client_email.replace("@", "%40")
                ),
            })
            firebase_admin.initialize_app(cred, {
                "storageBucket": storage_bucket
            })

        _firebase_auth = auth
        _storage_bucket = storage.bucket()
        logger.info("Firebase Admin SDK initialised (Auth + Storage).")
    except Exception as e:
        logger.error("Failed to initialise Firebase Admin SDK: %s", e, exc_info=True)



def verify_firebase_identity(token: str) -> dict[str, Any]:
    """Verify the Firebase signature without granting application access."""
    _init_firebase()
    if _firebase_auth is None:
        raise ValueError("Firebase Auth is not initialised.")
    try:
        return _firebase_auth.verify_id_token(token)
    except Exception as e:
        raise ValueError(f"Invalid Firebase token: {e}") from e


def grant_beta_access(uid: str) -> None:
    """Preserve any existing Firebase claims when marking a verified tester."""
    _init_firebase()
    if _firebase_auth is None:
        raise RuntimeError("Firebase Auth is not initialised.")
    record = _firebase_auth.get_user(uid)
    claims = dict(record.custom_claims or {})
    claims["beta_access"] = True
    _firebase_auth.set_custom_user_claims(uid, claims)


def verify_id_token(token: str) -> dict[str, Any]:
    """Verify the Firebase token and enforce the private beta gate."""
    claims = verify_firebase_identity(token)
    from app.config import settings
    if settings.DOCUMENT_DEMO:
        allowed_uids = {
            uid.strip()
            for uid in settings.DEMO_ALLOWED_UIDS.split(",")
            if uid.strip()
        }
        allowed_emails = {
            email.strip().lower()
            for email in settings.DEMO_ALLOWED_EMAILS.split(",")
            if email.strip()
        }
        claim_email = str(claims.get("email") or "").strip().lower()
        email_allowed = (
            bool(claim_email)
            and claims.get("email_verified") is True
            and claim_email in allowed_emails
        )
        if claims.get("uid") not in allowed_uids and not email_allowed and claims.get("beta_access") is not True:
            raise DemoAccessDenied(claims.get("uid", ""))
    return claims


def get_storage_bucket():
    """Return the Firebase Storage bucket handle."""
    _init_firebase()
    if _storage_bucket is None:
        raise RuntimeError("Firebase Storage is not initialised.")
    return _storage_bucket

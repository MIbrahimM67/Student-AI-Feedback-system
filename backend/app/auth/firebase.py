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


def _init_firebase():
    global _firebase_auth, _storage_bucket
    if _firebase_auth is not None:
        return

    project_id = os.environ.get("FIREBASE_PROJECT_ID", "")
    client_email = os.environ.get("FIREBASE_CLIENT_EMAIL", "")
    private_key = os.environ.get("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")
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
                "client_email": client_email,
                "private_key": private_key,
                "token_uri": "https://oauth2.googleapis.com/token",
            })
            firebase_admin.initialize_app(cred, {
                "storageBucket": storage_bucket
            })

        _firebase_auth = auth
        _storage_bucket = storage.bucket()
        logger.info("Firebase Admin SDK initialised (Auth + Storage).")
    except Exception as e:
        logger.error("Failed to initialise Firebase Admin SDK: %s", e)


def verify_id_token(token: str) -> dict[str, Any]:
    """
    Verify a Firebase ID token and return the decoded claims.
    Raises ValueError if the token is invalid.
    """
    _init_firebase()
    if _firebase_auth is None:
        raise ValueError("Firebase Auth is not initialised.")
    try:
        return _firebase_auth.verify_id_token(token)
    except Exception as e:
        raise ValueError(f"Invalid Firebase token: {e}") from e


def get_storage_bucket():
    """Return the Firebase Storage bucket handle."""
    _init_firebase()
    if _storage_bucket is None:
        raise RuntimeError("Firebase Storage is not initialised.")
    return _storage_bucket

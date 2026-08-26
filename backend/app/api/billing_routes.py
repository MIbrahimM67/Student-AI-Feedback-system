"""
GradeWise v3 — Billing and Subscription API Routes.

Endpoints:
  GET  /api/billing/plans                   → List plan features + current user status
  POST /api/billing/create-checkout-session → Start Stripe Checkout
  POST /api/billing/create-portal-session   → Customer Billing Portal (Self-serve)
  POST /api/billing/webhook                 → Stripe webhook handler
  POST /api/billing/sandbox-upgrade         → Instant demo upgrade (for presentation & sandbox)
"""
from __future__ import annotations

import logging
from typing import Optional, Literal
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from pydantic import BaseModel

from app.firebase import verify_firebase_token
from app.db.postgres import get_conn
from app.services.stripe_service import stripe_service, PLANS

router = APIRouter()
logger = logging.getLogger(__name__)


# ---- Dependency helpers -----------------------------------------------------

async def _get_current_user(token_payload: dict = Depends(verify_firebase_token)) -> dict:
    uid = token_payload.get("uid")
    if not uid:
        raise HTTPException(401, "Invalid authentication token.")
    
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT u.*, o.name as org_name
            FROM users u
            JOIN organizations o ON o.id = u.org_id
            WHERE u.uid = $1
            """,
            uid
        )
    if not row:
        raise HTTPException(404, "User profile not found.")
    return dict(row)


# ---- Schemas ----------------------------------------------------------------

class CheckoutRequest(BaseModel):
    plan_id: Literal["pro", "institution"]
    billing_cycle: Literal["monthly", "yearly"] = "monthly"
    promo_code: Optional[str] = None


class RedeemCodeRequest(BaseModel):
    code: str
    plan_id: Literal["pro", "institution"] = "pro"


class SandboxUpgradeRequest(BaseModel):
    plan_id: Literal["free", "pro", "institution"] = "pro"


# ---- Helper -----------------------------------------------------------------

def _check_faculty_eligibility(user: dict):
    role = user.get("role")
    faculty_status = user.get("faculty_status")
    if role == "admin":
        return
    if role == "instructor" and faculty_status == "approved":
        return
    raise HTTPException(
        status_code=403,
        detail="Pro subscriptions are reserved for verified faculty members. Please ensure your faculty application has been approved by an administrator."
    )


# ---- Endpoints --------------------------------------------------------------

@router.get("/plans")
async def get_plans_and_status(user: dict = Depends(_get_current_user)):
    """Returns available pricing plans and current user's subscription metadata."""
    current_plan = user.get("plan") or ("pro" if user.get("pro_status") == "active" else "free")
    is_eligible = user.get("role") == "admin" or (user.get("role") == "instructor" and user.get("faculty_status") == "approved")
    
    return {
        "plans": PLANS,
        "is_stripe_live": stripe_service.is_configured,
        "is_faculty_approved": user.get("faculty_status") == "approved" or user.get("role") == "admin",
        "is_eligible": is_eligible,
        "subscription": {
            "uid": user["uid"],
            "role": user.get("role"),
            "faculty_status": user.get("faculty_status"),
            "current_plan": current_plan,
            "pro_status": user.get("pro_status", "inactive"),
            "subscription_status": user.get("subscription_status", "inactive"),
            "current_period_end": user.get("current_period_end"),
            "has_stripe_customer": bool(user.get("stripe_customer_id")),
        }
    }


@router.post("/redeem-code")
async def redeem_promo_code(
    body: RedeemCodeRequest,
    user: dict = Depends(_get_current_user),
):
    """
    Validates a discount/promo code. The code 'testingphase' grants 100% discount,
    skipping payment processing and activating Pro status immediately.
    """
    _check_faculty_eligibility(user)

    code = body.code.strip().lower()
    if code != "testingphase":
        raise HTTPException(400, "Invalid or expired promo code.")

    result = await stripe_service.sandbox_activate(
        uid=user["uid"],
        plan_id=body.plan_id
    )
    result["message"] = f"🎉 Promo code '{body.code.strip()}' applied! 100% discount granted — {body.plan_id.upper()} subscription is now active."
    return result


@router.post("/create-checkout-session")
async def create_checkout_session(
    body: CheckoutRequest,
    request: Request,
    user: dict = Depends(_get_current_user),
):
    """
    Creates a Stripe Checkout Session. Returns checkout URL to redirect the user to.
    If promo code 'testingphase' is passed, skips payment and activates immediately.
    """
    _check_faculty_eligibility(user)

    if body.promo_code and body.promo_code.strip().lower() == "testingphase":
        result = await stripe_service.sandbox_activate(uid=user["uid"], plan_id=body.plan_id)
        return {
            "url": f"{request.headers.get('origin', '')}/?billing=success",
            "mode": "promo",
            "message": "Promo code 'testingphase' applied. Pro status activated!"
        }

    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        origin = f"{parsed.scheme}://{parsed.netloc}"

    try:
        session_data = await stripe_service.create_checkout_session(
            uid=user["uid"],
            email=user["email"],
            plan_id=body.plan_id,
            billing_cycle=body.billing_cycle,
            org_id=user.get("org_id"),
            origin_url=origin,
        )
        return session_data
    except Exception as e:
        logger.error("Checkout session creation failed: %s", e)
        raise HTTPException(400, str(e))


@router.post("/create-portal-session")
async def create_portal_session(
    request: Request,
    user: dict = Depends(_get_current_user),
):
    """
    Creates a Stripe Customer Portal session for managing/canceling subscriptions.
    """
    origin = request.headers.get("origin") or request.headers.get("referer")
    if origin:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        origin = f"{parsed.scheme}://{parsed.netloc}"

    try:
        portal_data = await stripe_service.create_portal_session(
            uid=user["uid"],
            origin_url=origin,
        )
        return portal_data
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Portal session creation failed: %s", e)
        raise HTTPException(400, str(e))


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """
    Stripe Webhook listener endpoint for asynchronous subscription lifecycle events.
    """
    if not stripe_signature:
        raise HTTPException(400, "Missing stripe-signature header.")

    payload_bytes = await request.body()
    try:
        result = await stripe_service.handle_webhook(payload_bytes, stripe_signature)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        logger.error("Webhook processing error: %s", e)
        raise HTTPException(500, "Webhook processing error.")


@router.post("/sandbox-upgrade")
async def sandbox_upgrade(
    body: SandboxUpgradeRequest,
    user: dict = Depends(_get_current_user),
):
    """
    Allows developers, evaluators, and presentation reviewers to toggle Pro status
    instantly in sandbox/demo mode without requiring a real credit card.
    """
    result = await stripe_service.sandbox_activate(
        uid=user["uid"],
        plan_id=body.plan_id
    )
    return result

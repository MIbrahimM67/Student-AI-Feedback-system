"""
GradeWise v3 — Stripe Payments and Subscription Service.

Handles:
- Customer creation & lookup
- Stripe Checkout Session creation (Monthly / Annual subscriptions)
- Customer Billing Portal for subscription management & invoices
- Webhook signature validation and database synchronization
- Sandbox / Dev mode fallback when Stripe credentials are not yet configured
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from app.config import settings
from app.db.postgres import get_conn

logger = logging.getLogger(__name__)

# Plan Definitions & Pricing (Single Source of Truth)
PLANS = {
    "free": {
        "id": "free",
        "name": "Free Tier",
        "description": "Essential grading workbench for students and individual trials",
        "price_monthly": 0,
        "price_yearly": 0,
        "limits": {
            "submissions_per_month": 5,
            "max_batch_size": 1,
            "deep_vision_enabled": False,
            "dedicated_inference_enabled": False,
            "internet_plagiarism_enabled": False,
            "pdf_export_enabled": True,
            "subjects_limit": 1,
        },
        "features": [
            "5 Submissions / month",
            "Single file uploads (PDF, DOCX, TXT, Code)",
            "Basic AI rubric feedback",
            "Standard OCR scanning",
            "Individual feedback scorecard",
        ]
    },
    "pro": {
        "id": "pro",
        "name": "Pro Instructor",
        "description": "Advanced multi-modal grading engine for faculty & professors",
        "price_monthly": 29,
        "price_yearly": 290,  # ~17% discount
        "limits": {
            "submissions_per_month": -1,  # unlimited
            "max_batch_size": 30,
            "deep_vision_enabled": True,
            "dedicated_inference_enabled": True,
            "internet_plagiarism_enabled": True,
            "pdf_export_enabled": True,
            "subjects_limit": 20,
        },
        "features": [
            "Unlimited single & batch uploads (up to 30 files/ZIP)",
            "3-Stage Evaluation Pipeline (Specialist + Judge + Senior)",
            "Deep Vision Multi-Modal OCR for handwritten scans & diagrams",
            "Internet Web Search & Cross-batch Plagiarism Indexing",
            "Subject Knowledge Graph (Textbooks, Schemes & Syllabi)",
            "One-click Publication-Grade PDF Reports & Excel Gradebooks",
            "Live student name extraction & inline editing",
        ]
    },
    "institution": {
        "id": "institution",
        "name": "Institution & Department",
        "description": "Campus-wide grading platform for universities & departments",
        "price_monthly": 199,
        "price_yearly": 1990,
        "limits": {
            "submissions_per_month": -1,
            "max_batch_size": 100,
            "deep_vision_enabled": True,
            "dedicated_inference_enabled": True,
            "internet_plagiarism_enabled": True,
            "pdf_export_enabled": True,
            "subjects_limit": -1,
        },
        "features": [
            "Everything in Pro Instructor plan",
            "Multi-instructor department shared workspace",
            "Dedicated high-throughput GPU inference queues",
            "Centralized Faculty Verification & Admin Audit Logs",
            "Priority Support & Custom Rubric Templates",
            "Custom LMS / Webhook Integration options",
        ]
    }
}


class StripeService:
    def __init__(self):
        self._stripe = None
        self._init_stripe()

    def _init_stripe(self):
        if settings.STRIPE_SECRET_KEY:
            try:
                import stripe
                stripe.api_key = settings.STRIPE_SECRET_KEY
                self._stripe = stripe
                logger.info("Stripe client initialized successfully.")
            except Exception as e:
                logger.warning("Could not initialize Stripe SDK: %s", e)
        else:
            logger.info("STRIPE_SECRET_KEY not set; running in Sandbox / Demo mode.")

    @property
    def is_configured(self) -> bool:
        return self._stripe is not None and bool(settings.STRIPE_SECRET_KEY)

    async def get_or_create_customer(self, uid: str, email: str, name: Optional[str] = None) -> Optional[str]:
        """Look up or create a Stripe customer for a GradeWise user."""
        if not self.is_configured:
            return f"mock_cus_{uid[:12]}"

        # Check if customer id is already stored in DB
        async with get_conn() as conn:
            row = await conn.fetchrow("SELECT stripe_customer_id FROM users WHERE uid = $1", uid)
            if row and row["stripe_customer_id"]:
                return row["stripe_customer_id"]

        try:
            # Create in Stripe
            customer = self._stripe.Customer.create(
                email=email,
                name=name or email,
                metadata={"uid": uid}
            )
            customer_id = customer.id

            async with get_conn() as conn:
                await conn.execute(
                    "UPDATE users SET stripe_customer_id = $1 WHERE uid = $2",
                    customer_id, uid
                )
            return customer_id
        except Exception as e:
            logger.error("Failed to create Stripe customer for %s: %s", uid, e)
            return None

    async def create_checkout_session(
        self,
        uid: str,
        email: str,
        plan_id: str,
        billing_cycle: str = "monthly",  # 'monthly' | 'yearly'
        org_id: Optional[str] = None,
        origin_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Creates a Stripe Checkout Session for subscribing to Pro or Institution."""
        plan = PLANS.get(plan_id)
        if not plan or plan_id == "free":
            raise ValueError("Invalid plan selected for checkout.")

        base_url = origin_url or settings.FRONTEND_URL or "http://localhost:3000"
        success_url = f"{base_url}/?billing=success&session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{base_url}/?billing=canceled"

        if not self.is_configured:
            # Development / Sandbox Mode URL
            logger.info("Stripe not configured — generating sandbox activation response for plan: %s", plan_id)
            return {
                "url": f"{base_url}/?billing=sandbox_success&plan={plan_id}",
                "mode": "sandbox",
                "message": "Running in Demo/Sandbox mode. Use 'Activate Demo Pro' to test instantly without real card processing."
            }

        customer_id = await self.get_or_create_customer(uid, email)
        
        # Select price or create custom line item
        price_amount = plan["price_yearly"] * 100 if billing_cycle == "yearly" else plan["price_monthly"] * 100
        interval = "year" if billing_cycle == "yearly" else "month"

        try:
            session = self._stripe.checkout.Session.create(
                mode="subscription",
                payment_method_types=["card"],
                customer=customer_id,
                customer_email=None if customer_id else email,
                line_items=[{
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"GradeWise {plan['name']}",
                            "description": plan["description"],
                        },
                        "unit_amount": price_amount,
                        "recurring": {
                            "interval": interval,
                        },
                    },
                    "quantity": 1,
                }],
                subscription_data={
                    "metadata": {
                        "uid": uid,
                        "plan_id": plan_id,
                        "org_id": str(org_id) if org_id else "",
                    }
                },
                metadata={
                    "uid": uid,
                    "plan_id": plan_id,
                    "org_id": str(org_id) if org_id else "",
                },
                success_url=success_url,
                cancel_url=cancel_url,
            )
            return {"url": session.url, "session_id": session.id, "mode": "stripe"}
        except Exception as e:
            logger.error("Failed to create Stripe checkout session: %s", e)
            raise RuntimeError(f"Stripe checkout error: {str(e)}")

    async def create_portal_session(self, uid: str, origin_url: Optional[str] = None) -> Dict[str, Any]:
        """Creates a Stripe Customer Billing Portal session for managing/canceling subscriptions."""
        base_url = origin_url or settings.FRONTEND_URL or "http://localhost:3000"
        return_url = f"{base_url}/"

        if not self.is_configured:
            return {
                "url": f"{base_url}/?billing=sandbox_portal",
                "mode": "sandbox",
                "message": "Demo mode: You can switch or toggle subscription states anytime from the dashboard."
            }

        async with get_conn() as conn:
            row = await conn.fetchrow("SELECT stripe_customer_id FROM users WHERE uid = $1", uid)
            customer_id = row["stripe_customer_id"] if row else None

        if not customer_id:
            raise ValueError("No active Stripe customer found for this account.")

        try:
            portal_session = self._stripe.billingPortal.Session.create(
                customer=customer_id,
                return_url=return_url,
            )
            return {"url": portal_session.url}
        except Exception as e:
            logger.error("Failed to create billing portal session: %s", e)
            raise RuntimeError(f"Billing portal error: {str(e)}")

    async def handle_webhook(self, payload_bytes: bytes, sig_header: str) -> Dict[str, Any]:
        """Validates and processes Stripe webhook events."""
        if not self.is_configured:
            return {"status": "ignored", "reason": "stripe_not_configured"}

        if not settings.STRIPE_WEBHOOK_SECRET:
            logger.warning("STRIPE_WEBHOOK_SECRET not set; cannot verify webhook signature.")
            return {"status": "ignored", "reason": "webhook_secret_missing"}

        try:
            event = self._stripe.Webhook.construct_event(
                payload_bytes, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
        except Exception as e:
            logger.error("Invalid Stripe webhook signature: %s", e)
            raise ValueError(f"Webhook signature error: {str(e)}")

        event_type = event["type"]
        data_object = event["data"]["object"]
        now = datetime.now(timezone.utc)

        logger.info("Processing Stripe webhook event: %s", event_type)

        if event_type == "checkout.session.completed":
            uid = data_object.get("metadata", {}).get("uid")
            plan_id = data_object.get("metadata", {}).get("plan_id", "pro")
            sub_id = data_object.get("subscription")
            cus_id = data_object.get("customer")

            if uid:
                org_id = await _org_for_uid(uid)
                async with get_conn(org_id) as conn:
                    await conn.execute(
                        """
                        UPDATE users SET
                          pro_status = 'active',
                          plan = $1,
                          subscription_status = 'active',
                          stripe_customer_id = COALESCE($2, stripe_customer_id),
                          stripe_subscription_id = $3,
                          updated_at = $4
                        WHERE uid = $5
                        """,
                        plan_id, cus_id, sub_id, now, uid
                    )
                logger.info("Successfully activated Pro status for user %s via Stripe checkout", uid)

        elif event_type in ("customer.subscription.updated", "customer.subscription.deleted"):
            sub_id = data_object.get("id")
            status = data_object.get("status")  # 'active', 'past_due', 'canceled', 'trialing'
            period_end = data_object.get("current_period_end")
            period_end_dt = datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None
            uid = data_object.get("metadata", {}).get("uid")

            pro_state = "active" if status in ("active", "trialing") else "inactive"
            plan_name = data_object.get("metadata", {}).get("plan_id", "pro") if pro_state == "active" else "free"

            org_id = await _org_for_uid(uid) if uid else None
            async with get_conn(org_id) as conn:
                if uid:
                    await conn.execute(
                        """
                        UPDATE users SET
                          pro_status = $1,
                          plan = $2,
                          subscription_status = $3,
                          current_period_end = $4,
                          updated_at = $5
                        WHERE uid = $6
                        """,
                        pro_state, plan_name, status, period_end_dt, now, uid
                    )
                else:
                    await conn.execute(
                        """
                        UPDATE users SET
                          pro_status = $1,
                          plan = $2,
                          subscription_status = $3,
                          current_period_end = $4,
                          updated_at = $5
                        WHERE stripe_subscription_id = $6
                        """,
                        pro_state, plan_name, status, period_end_dt, now, sub_id
                    )
            logger.info("Updated subscription for sub %s to status: %s (pro_status=%s)", sub_id, status, pro_state)

        return {"status": "success", "event": event_type}

    async def sandbox_activate(self, uid: str, plan_id: str = "pro") -> Dict[str, Any]:
        """Instantly toggles a user's subscription for demo and FYP presentation purposes."""
        now = datetime.now(timezone.utc)
        plan = PLANS.get(plan_id, PLANS["pro"])
        pro_status = "active" if plan_id in ("pro", "institution") else "inactive"

        org_id = await _org_for_uid(uid)
        if not org_id:
            raise ValueError("User profile not found.")
        # Row-level security hides users unless the tenant context is set.
        async with get_conn(org_id) as conn:
            result = await conn.execute(
                """
                UPDATE users SET
                  pro_status = $1,
                  plan = $2,
                  subscription_status = $3,
                  updated_at = $4
                WHERE uid = $5
                """,
                pro_status, plan_id, "active" if pro_status == "active" else "inactive", now, uid
            )
        if result == "UPDATE 0":
            raise ValueError("Subscription was not updated.")
        return {
            "status": "success",
            "uid": uid,
            "plan": plan_id,
            "pro_status": pro_status,
            "message": f"Successfully updated subscription to {plan['name']}!"
        }


async def _org_for_uid(uid: str) -> Optional[str]:
    async with get_conn() as conn:
        org_id = await conn.fetchval("SELECT get_user_org_id($1)", uid)
    return str(org_id) if org_id else None


stripe_service = StripeService()

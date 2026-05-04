"""Billing router: subscription page, Stripe Checkout, portal, and webhooks."""

from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.plan_access import get_plan_mode
from app.services import billing_service

router = APIRouter(tags=["billing"])
templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger(__name__)


@router.get("/billing/subscribe", response_class=HTMLResponse)
async def billing_subscribe(
    request: Request,
    msg: str = "",
    msg_type: str = "info",
    current_user: User = Depends(require_user),
):
    """Show the subscription / upgrade page."""
    plan_mode = get_plan_mode(current_user)
    stripe_any_configured = bool(
        settings.STRIPE_SECRET_KEY
        and any(
            [
                settings.STRIPE_PRICE_ID_BASIC,
                settings.STRIPE_PRICE_ID_PREMIUM,
                settings.STRIPE_PRICE_ID_ENTERPRISE,
                settings.STRIPE_PRICE_ID,
            ]
        )
    )
    return templates.TemplateResponse(
        request,
        "billing/subscribe.html",
        {
            "request": request,
            "current_user": current_user,
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "stripe_configured": stripe_any_configured,
            "plan_mode": plan_mode,
            "basic_configured": bool(
                settings.STRIPE_PRICE_ID_BASIC or settings.STRIPE_PRICE_ID
            ),
            "premium_configured": bool(settings.STRIPE_PRICE_ID_PREMIUM),
            "enterprise_configured": bool(settings.STRIPE_PRICE_ID_ENTERPRISE),
            "msg": msg,
            "msg_type": msg_type,
        },
    )


@router.post("/billing/checkout")
async def billing_checkout(
    request: Request,
    plan: str = Form(default="basic"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a Stripe Checkout session and redirect the user to Stripe."""
    allowed_plans = ("basic", "premium", "enterprise")
    if plan not in allowed_plans:
        plan = "basic"
    try:
        url = await billing_service.create_checkout_session(
            current_user.active_tenant,
            current_user,
            db,
            plan=plan,  # type: ignore[attr-defined]
        )
    except RuntimeError as exc:
        logger.exception("Checkout session creation failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return RedirectResponse(url, status_code=303)


@router.post("/billing/upgrade")
async def billing_upgrade(
    request: Request,
    plan: str = Form(default="premium"),
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Upgrade or downgrade to a new plan.

    Upgrades → Stripe Checkout (prorated payment today).
    Downgrades → schedule the price change for next renewal, no charge today.
    """
    allowed_plans = ("basic", "premium", "enterprise")
    if plan not in allowed_plans:
        plan = "premium"

    tenant = current_user.active_tenant

    if billing_service.is_downgrade(tenant.plan, plan):
        try:
            await billing_service.schedule_downgrade(tenant, plan, db)
        except RuntimeError as exc:
            logger.exception("Downgrade scheduling failed: %s", exc)
            return RedirectResponse(
                f"/billing/subscribe?msg={exc}&msg_type=danger", status_code=303
            )
        plan_label = plan.capitalize()
        return RedirectResponse(
            f"/billing/subscribe?msg=Tu plan bajará a {plan_label} al renovarse&msg_type=info",
            status_code=303,
        )

    try:
        url = await billing_service.create_upgrade_checkout_session(
            tenant,
            current_user,
            plan,
            db,
        )
    except RuntimeError as exc:
        logger.exception("Upgrade checkout creation failed: %s", exc)
        return RedirectResponse(
            f"/billing/subscribe?msg={exc}&msg_type=danger", status_code=303
        )

    return RedirectResponse(url, status_code=303)


@router.get("/billing/success", response_class=HTMLResponse)
async def billing_success(
    request: Request,
    session_id: str = "",
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Show a success page after a successful Stripe Checkout.

    Also acts as a safety net: if the webhook has not yet been delivered,
    fulfill_checkout_session activates the subscription proactively.
    """
    if session_id:
        try:
            activated = await billing_service.fulfill_checkout_session(session_id, db)
            if activated and current_user.active_tenant:
                # Refresh the tenant in-memory so the session reflects the just-activated
                # plan immediately (require_user ran before fulfill committed to DB).
                from datetime import UTC, datetime
                await db.refresh(current_user.active_tenant)
                tenant = current_user.active_tenant
                request.session["tenant_plan"] = tenant.plan
                request.session["subscription_status"] = tenant.subscription_status
                if tenant.subscription_ends_at:
                    delta = tenant.subscription_ends_at - datetime.now(UTC)
                    request.session["subscription_days_left"] = delta.days
                else:
                    request.session["subscription_days_left"] = None
        except Exception as exc:
            logger.exception("fulfill_checkout_session failed: %s", exc)

    return templates.TemplateResponse(
        request,
        "billing/success.html",
        {"request": request, "current_user": current_user},
    )


@router.get("/billing/cancel", response_class=HTMLResponse)
async def billing_cancel(
    request: Request,
    current_user: User = Depends(require_user),
):
    """Show a cancel page when the user abandons Stripe Checkout."""
    return templates.TemplateResponse(
        request,
        "billing/cancel.html",
        {"request": request, "current_user": current_user},
    )


@router.post("/billing/portal")
async def billing_portal(
    request: Request,
    current_user: User = Depends(require_user),
):
    """Redirect the user to the Stripe Customer Portal to manage their subscription."""
    try:
        url = await billing_service.create_portal_session(
            current_user.active_tenant  # type: ignore[attr-defined]
        )
    except RuntimeError as exc:
        logger.exception("Portal session creation failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return RedirectResponse(url, status_code=303)


@router.post("/billing/stripe/webhook")
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Receive and process Stripe webhook events.

    IMPORTANT: we must read raw bytes BEFORE any JSON parsing so that the
    Stripe signature computed over the raw body matches.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        await billing_service.handle_webhook(payload, sig_header, db)
    except stripe.SignatureVerificationError:
        logger.warning("Stripe webhook: invalid signature")
        raise HTTPException(status_code=400, detail="Invalid Stripe signature")
    except RuntimeError as exc:
        logger.exception("Stripe webhook handler error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return {"ok": True}

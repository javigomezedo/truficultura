"""Billing router: subscription page, Stripe Checkout, portal, and webhooks."""

from __future__ import annotations

import logging

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user, is_subscription_blocked
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services import billing_service

router = APIRouter(tags=["billing"])
templates = Jinja2Templates(directory="app/templates")

logger = logging.getLogger(__name__)


@router.get("/billing/subscribe", response_class=HTMLResponse)
async def billing_subscribe(
    request: Request,
    current_user: User = Depends(require_user),
):
    """Show the subscription / upgrade page."""
    return templates.TemplateResponse(
        request,
        "billing/subscribe.html",
        {
            "request": request,
            "current_user": current_user,
            "stripe_publishable_key": settings.STRIPE_PUBLISHABLE_KEY,
            "stripe_configured": bool(
                settings.STRIPE_SECRET_KEY and settings.STRIPE_PRICE_ID
            ),
            "subscription_is_blocked": is_subscription_blocked(current_user),
        },
    )


@router.post("/billing/checkout")
async def billing_checkout(
    request: Request,
    current_user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a Stripe Checkout session and redirect the user to Stripe."""
    try:
        url = await billing_service.create_checkout_session(current_user, db)
    except RuntimeError as exc:
        logger.error("Checkout session creation failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return RedirectResponse(url, status_code=303)


@router.get("/billing/success", response_class=HTMLResponse)
async def billing_success(
    request: Request,
    current_user: User = Depends(require_user),
):
    """Show a success page after a successful Stripe Checkout."""
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
        url = await billing_service.create_portal_session(current_user)
    except RuntimeError as exc:
        logger.error("Portal session creation failed: %s", exc)
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
        logger.error("Stripe webhook handler error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc))

    return {"ok": True}

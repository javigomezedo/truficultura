"""Billing service: Stripe integration for trial + annual subscription."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import stripe
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services.email_service import (
    send_payment_failed_email,
    send_subscription_activated_email,
    send_subscription_canceled_email,
    send_subscription_renewed_email,
)

logger = logging.getLogger(__name__)


def _stripe_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def _get_stripe_client() -> stripe.StripeClient:
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY)


async def start_trial(user: User, db: AsyncSession) -> None:
    """Set subscription_status=trialing and trial_ends_at=now+TRIAL_DAYS."""
    user.subscription_status = "trialing"
    user.trial_ends_at = datetime.now(UTC) + timedelta(days=settings.TRIAL_DAYS)
    await db.commit()


async def get_or_create_stripe_customer(user: User, db: AsyncSession) -> str:
    """Return existing stripe_customer_id or create a new Stripe customer.

    Returns the customer ID string. Raises RuntimeError if Stripe is not configured.
    """
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured (STRIPE_SECRET_KEY missing).")

    if user.stripe_customer_id:
        return user.stripe_customer_id

    client = _get_stripe_client()
    customer = client.customers.create(
        params={
            "email": user.email,
            "name": f"{user.first_name} {user.last_name}".strip(),
            "metadata": {"user_id": str(user.id)},
        }
    )
    user.stripe_customer_id = customer.id
    await db.commit()
    return customer.id


async def create_checkout_session(user: User, db: AsyncSession) -> str:
    """Create a Stripe Checkout session for the annual plan and return the URL.

    Trial is managed by the app, not by Stripe, so no trial_period_days is set here.
    The checkout redirects to billing/success on completion and billing/cancel on abort.
    """
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured.")
    if not settings.STRIPE_PRICE_ID:
        raise RuntimeError("STRIPE_PRICE_ID is not configured.")

    customer_id = await get_or_create_stripe_customer(user, db)
    client = _get_stripe_client()

    session = client.checkout.sessions.create(
        params={
            "customer": customer_id,
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price": settings.STRIPE_PRICE_ID,
                    "quantity": 1,
                }
            ],
            "mode": "subscription",
            "success_url": f"{settings.APP_BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{settings.APP_BASE_URL}/billing/cancel",
            "metadata": {"user_id": str(user.id)},
        }
    )
    return session.url


async def create_portal_session(user: User) -> str:
    """Create a Stripe Customer Portal session and return the URL."""
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured.")
    if not user.stripe_customer_id:
        raise RuntimeError("User has no Stripe customer ID.")

    client = _get_stripe_client()
    session = client.billing_portal.sessions.create(
        params={
            "customer": user.stripe_customer_id,
            "return_url": f"{settings.APP_BASE_URL}/billing/subscribe",
        }
    )
    return session.url


async def handle_webhook(
    payload: bytes,
    stripe_signature: str,
    db: AsyncSession,
) -> None:
    """Verify Stripe webhook signature and process the event.

    Raises stripe.SignatureVerificationError if the signature is invalid.
    Raises RuntimeError if STRIPE_WEBHOOK_SECRET is not configured.
    """
    if not settings.STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET is not configured.")

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.SignatureVerificationError:
        raise

    event_type: str = event["type"]
    data_object = event["data"]["object"]

    logger.info("Stripe webhook received: %s", event_type)

    if event_type == "checkout.session.completed":
        await _handle_checkout_completed(data_object, db)
    elif event_type == "invoice.paid":
        await _handle_invoice_paid(data_object, db)
    elif event_type == "invoice.payment_failed":
        await _handle_invoice_payment_failed(data_object, db)
    elif event_type == "customer.subscription.updated":
        await _handle_subscription_updated(data_object, db)
    elif event_type == "customer.subscription.deleted":
        await _handle_subscription_deleted(data_object, db)


# ── Internal handlers ──────────────────────────────────────────────────────────


async def _get_user_by_customer_id(customer_id: str, db: AsyncSession) -> User | None:
    from sqlalchemy import select

    result = await db.execute(
        select(User).where(User.stripe_customer_id == customer_id)
    )
    return result.scalar_one_or_none()


async def _handle_checkout_completed(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    user = await _get_user_by_customer_id(customer_id, db)
    if not user:
        logger.warning(
            "checkout.session.completed: no user for customer %s", customer_id
        )
        return

    # Retrieve the subscription to get period_end
    subscription_id = data_object.subscription
    if subscription_id:
        client = _get_stripe_client()
        sub = client.subscriptions.retrieve(subscription_id)
        # current_period_end moved to items in newer Stripe API versions
        period_end = getattr(sub, "current_period_end", None)
        if period_end is None:
            try:
                period_end = sub.items.data[0].current_period_end
            except (AttributeError, IndexError, TypeError):
                period_end = None
        if period_end:
            user.subscription_ends_at = datetime.fromtimestamp(period_end, tz=UTC)

    user.subscription_status = "active"
    await db.commit()
    logger.info("User %s activated subscription.", user.id)
    ends_at_str = (
        user.subscription_ends_at.strftime("%d/%m/%Y")
        if user.subscription_ends_at
        else None
    )
    try:
        await send_subscription_activated_email(user.email, ends_at_str)
    except Exception as exc:
        logger.warning(
            "[billing] Could not send activation email to %s: %s", user.email, exc
        )


async def _handle_invoice_paid(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    user = await _get_user_by_customer_id(customer_id, db)
    if not user:
        return

    # period_end is on the lines for subscription invoices
    period_end = None
    lines_data = getattr(getattr(data_object, "lines", None), "data", [])
    for line in lines_data:
        line_period = getattr(line, "period", None)
        if line_period and getattr(line_period, "end", None):
            period_end = line_period.end
            break

    if period_end:
        user.subscription_ends_at = datetime.fromtimestamp(period_end, tz=UTC)

    user.subscription_status = "active"
    await db.commit()
    logger.info("User %s subscription renewed.", user.id)

    # Only send renewal email for actual renewals, not the first invoice
    # (which is already covered by the checkout.session.completed handler)
    billing_reason = getattr(data_object, "billing_reason", None)
    if billing_reason == "subscription_cycle":
        ends_at_str = (
            user.subscription_ends_at.strftime("%d/%m/%Y")
            if user.subscription_ends_at
            else None
        )
        try:
            await send_subscription_renewed_email(user.email, ends_at_str)
        except Exception as exc:
            logger.warning(
                "[billing] Could not send renewal email to %s: %s", user.email, exc
            )


async def _handle_invoice_payment_failed(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    user = await _get_user_by_customer_id(customer_id, db)
    if not user:
        return

    user.subscription_status = "past_due"
    await db.commit()
    logger.warning("User %s payment failed — status set to past_due.", user.id)
    try:
        await send_payment_failed_email(user.email)
    except Exception as exc:
        logger.warning(
            "[billing] Could not send payment-failed email to %s: %s", user.email, exc
        )


async def _handle_subscription_updated(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    user = await _get_user_by_customer_id(customer_id, db)
    if not user:
        return

    stripe_status = getattr(data_object, "status", None)
    cancel_at_period_end = getattr(data_object, "cancel_at_period_end", False)

    # Sync subscription_ends_at from current_period_end (or items fallback)
    period_end = getattr(data_object, "current_period_end", None)
    if period_end is None:
        try:
            period_end = data_object.items.data[0].current_period_end
        except (AttributeError, IndexError, TypeError):
            period_end = None
    if period_end:
        user.subscription_ends_at = datetime.fromtimestamp(period_end, tz=UTC)

    # Map Stripe status → app status
    if stripe_status == "active":
        user.subscription_status = "active"
    elif stripe_status == "past_due":
        user.subscription_status = "past_due"
    elif stripe_status in ("canceled", "unpaid", "incomplete_expired"):
        user.subscription_status = "canceled"

    if cancel_at_period_end:
        logger.info(
            "User %s subscription will cancel at period end (%s).",
            user.id,
            user.subscription_ends_at,
        )

        # Stripe marks user as active until the period ends. Notify here so
        # users receive the cancellation confirmation at request time.
        if stripe_status == "active":
            ends_at_str = (
                user.subscription_ends_at.strftime("%d/%m/%Y")
                if user.subscription_ends_at
                else None
            )
            logger.info(
                "[billing] Sending scheduled-cancellation email to %s (ends_at=%s)",
                user.email,
                ends_at_str,
            )
            try:
                await send_subscription_canceled_email(user.email, ends_at_str)
            except Exception as exc:
                logger.warning(
                    "[billing] Could not send scheduled-cancellation email to %s: %s",
                    user.email,
                    exc,
                )
    else:
        logger.info(
            "User %s subscription updated — status=%s.",
            user.id,
            user.subscription_status,
        )

    await db.commit()


async def _handle_subscription_deleted(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    user = await _get_user_by_customer_id(customer_id, db)
    if not user:
        return

    user.subscription_status = "canceled"
    await db.commit()
    logger.info("User %s subscription canceled.", user.id)
    ends_at_str = (
        user.subscription_ends_at.strftime("%d/%m/%Y")
        if user.subscription_ends_at
        else None
    )
    logger.info(
        "[billing] Sending cancellation email to %s (ends_at=%s)",
        user.email,
        ends_at_str,
    )
    try:
        await send_subscription_canceled_email(user.email, ends_at_str)
    except Exception as exc:
        logger.warning(
            "[billing] Could not send cancellation email to %s: %s", user.email, exc
        )

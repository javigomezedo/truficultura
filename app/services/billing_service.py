"""Billing service: Stripe integration for trial + annual subscription."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.tenant import Tenant, TenantMembership
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


async def _get_tenant_by_customer_id(
    customer_id: str, db: AsyncSession
) -> Tenant | None:
    result = await db.execute(
        select(Tenant).where(Tenant.stripe_customer_id == customer_id)
    )
    return result.scalar_one_or_none()


async def _get_owner_email_for_tenant(
    tenant: Tenant, db: AsyncSession
) -> str | None:
    """Return the email of the tenant's owner user for notification emails."""
    result = await db.execute(
        select(User)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(
            TenantMembership.tenant_id == tenant.id,
            TenantMembership.role == "owner",
        )
    )
    owner = result.scalar_one_or_none()
    return owner.email if owner else None


async def start_trial(tenant: Tenant, db: AsyncSession) -> None:
    """Set subscription_status=trialing and trial_ends_at=now+TRIAL_DAYS on the tenant."""
    tenant.subscription_status = "trialing"
    tenant.trial_ends_at = datetime.now(UTC) + timedelta(days=settings.TRIAL_DAYS)
    await db.commit()


async def get_or_create_stripe_customer(
    tenant: Tenant, user: User, db: AsyncSession
) -> str:
    """Return existing stripe_customer_id or create a new Stripe customer.

    The Stripe customer is associated to the tenant (billing entity).
    The user email and name are used for display in the Stripe dashboard.
    """
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured (STRIPE_SECRET_KEY missing).")

    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id

    client = _get_stripe_client()
    customer = client.customers.create(
        params={
            "email": user.email,
            "name": f"{user.first_name} {user.last_name}".strip(),
            "metadata": {"tenant_id": str(tenant.id), "user_id": str(user.id)},
        }
    )
    tenant.stripe_customer_id = customer.id
    await db.commit()
    return customer.id


async def create_checkout_session(
    tenant: Tenant, user: User, db: AsyncSession
) -> str:
    """Create a Stripe Checkout session for the annual plan and return the URL."""
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured.")
    if not settings.STRIPE_PRICE_ID:
        raise RuntimeError("STRIPE_PRICE_ID is not configured.")

    customer_id = await get_or_create_stripe_customer(tenant, user, db)
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
            "metadata": {"tenant_id": str(tenant.id), "user_id": str(user.id)},
        }
    )
    return session.url


async def create_portal_session(tenant: Tenant) -> str:
    """Create a Stripe Customer Portal session and return the URL."""
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured.")
    if not tenant.stripe_customer_id:
        raise RuntimeError("Tenant has no Stripe customer ID.")

    client = _get_stripe_client()
    session = client.billing_portal.sessions.create(
        params={
            "customer": tenant.stripe_customer_id,
            "return_url": f"{settings.APP_BASE_URL}/billing/subscribe",
        }
    )
    return session.url


async def handle_webhook(
    payload: bytes,
    stripe_signature: str,
    db: AsyncSession,
) -> None:
    """Verify Stripe webhook signature and process the event."""
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


async def _handle_checkout_completed(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    tenant = await _get_tenant_by_customer_id(customer_id, db)
    if not tenant:
        logger.warning(
            "checkout.session.completed: no tenant for customer %s", customer_id
        )
        return

    subscription_id = data_object.subscription
    if subscription_id:
        client = _get_stripe_client()
        sub = client.subscriptions.retrieve(subscription_id)
        period_end = getattr(sub, "current_period_end", None)
        if period_end is None:
            try:
                period_end = sub.items.data[0].current_period_end
            except (AttributeError, IndexError, TypeError):
                period_end = None
        if period_end:
            tenant.subscription_ends_at = datetime.fromtimestamp(period_end, tz=UTC)

    tenant.subscription_status = "active"
    await db.commit()
    logger.info("Tenant %s activated subscription.", tenant.id)

    owner_email = await _get_owner_email_for_tenant(tenant, db)
    if owner_email:
        ends_at_str = (
            tenant.subscription_ends_at.strftime("%d/%m/%Y")
            if tenant.subscription_ends_at
            else None
        )
        try:
            await send_subscription_activated_email(owner_email, ends_at_str)
        except Exception as exc:
            logger.warning(
                "[billing] Could not send activation email to %s: %s", owner_email, exc
            )


async def _handle_invoice_paid(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    tenant = await _get_tenant_by_customer_id(customer_id, db)
    if not tenant:
        return

    period_end = None
    lines_data = getattr(getattr(data_object, "lines", None), "data", [])
    for line in lines_data:
        line_period = getattr(line, "period", None)
        if line_period and getattr(line_period, "end", None):
            period_end = line_period.end
            break

    if period_end:
        tenant.subscription_ends_at = datetime.fromtimestamp(period_end, tz=UTC)

    tenant.subscription_status = "active"
    await db.commit()
    logger.info("Tenant %s subscription renewed.", tenant.id)

    billing_reason = getattr(data_object, "billing_reason", None)
    if billing_reason == "subscription_cycle":
        owner_email = await _get_owner_email_for_tenant(tenant, db)
        if owner_email:
            ends_at_str = (
                tenant.subscription_ends_at.strftime("%d/%m/%Y")
                if tenant.subscription_ends_at
                else None
            )
            try:
                await send_subscription_renewed_email(owner_email, ends_at_str)
            except Exception as exc:
                logger.warning(
                    "[billing] Could not send renewal email to %s: %s", owner_email, exc
                )


async def _handle_invoice_payment_failed(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    tenant = await _get_tenant_by_customer_id(customer_id, db)
    if not tenant:
        return

    tenant.subscription_status = "past_due"
    await db.commit()
    logger.warning("Tenant %s payment failed — status set to past_due.", tenant.id)

    owner_email = await _get_owner_email_for_tenant(tenant, db)
    if owner_email:
        try:
            await send_payment_failed_email(owner_email)
        except Exception as exc:
            logger.warning(
                "[billing] Could not send payment-failed email to %s: %s", owner_email, exc
            )


async def _handle_subscription_updated(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    tenant = await _get_tenant_by_customer_id(customer_id, db)
    if not tenant:
        return

    stripe_status = getattr(data_object, "status", None)
    cancel_at_period_end = getattr(data_object, "cancel_at_period_end", False)

    period_end = getattr(data_object, "current_period_end", None)
    if period_end is None:
        try:
            period_end = data_object.items.data[0].current_period_end
        except (AttributeError, IndexError, TypeError):
            period_end = None
    if period_end:
        tenant.subscription_ends_at = datetime.fromtimestamp(period_end, tz=UTC)

    if stripe_status == "active":
        tenant.subscription_status = "active"
    elif stripe_status == "past_due":
        tenant.subscription_status = "past_due"
    elif stripe_status in ("canceled", "unpaid", "incomplete_expired"):
        tenant.subscription_status = "canceled"

    if cancel_at_period_end:
        logger.info(
            "Tenant %s subscription will cancel at period end (%s).",
            tenant.id,
            tenant.subscription_ends_at,
        )
        if stripe_status == "active":
            owner_email = await _get_owner_email_for_tenant(tenant, db)
            if owner_email:
                ends_at_str = (
                    tenant.subscription_ends_at.strftime("%d/%m/%Y")
                    if tenant.subscription_ends_at
                    else None
                )
                try:
                    await send_subscription_canceled_email(owner_email, ends_at_str)
                except Exception as exc:
                    logger.warning(
                        "[billing] Could not send scheduled-cancellation email to %s: %s",
                        owner_email,
                        exc,
                    )
    else:
        logger.info(
            "Tenant %s subscription updated — status=%s.",
            tenant.id,
            tenant.subscription_status,
        )

    await db.commit()


async def _handle_subscription_deleted(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    tenant = await _get_tenant_by_customer_id(customer_id, db)
    if not tenant:
        return

    tenant.subscription_status = "canceled"
    await db.commit()
    logger.info("Tenant %s subscription canceled.", tenant.id)

    owner_email = await _get_owner_email_for_tenant(tenant, db)
    if owner_email:
        ends_at_str = (
            tenant.subscription_ends_at.strftime("%d/%m/%Y")
            if tenant.subscription_ends_at
            else None
        )
        try:
            await send_subscription_canceled_email(owner_email, ends_at_str)
        except Exception as exc:
            logger.warning(
                "[billing] Could not send cancellation email to %s: %s", owner_email, exc
            )




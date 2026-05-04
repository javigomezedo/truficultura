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


async def _get_owner_email_for_tenant(tenant: Tenant, db: AsyncSession) -> str | None:
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


_PLAN_PRICE_MAP = {
    "basic": "STRIPE_PRICE_ID_BASIC",
    "premium": "STRIPE_PRICE_ID_PREMIUM",
    "enterprise": "STRIPE_PRICE_ID_ENTERPRISE",
}


def _resolve_price_id(plan: str) -> str:
    """Return the Stripe Price ID for *plan*, falling back to legacy STRIPE_PRICE_ID."""
    attr = _PLAN_PRICE_MAP.get(plan)
    if attr:
        price_id: str | None = getattr(settings, attr, None)
        if price_id:
            return price_id
    # Fallback to the legacy single price ID
    if settings.STRIPE_PRICE_ID:
        return settings.STRIPE_PRICE_ID
    raise RuntimeError(
        f"No Stripe Price ID configured for plan '{plan}'. "
        "Set STRIPE_PRICE_ID_BASIC / _PREMIUM / _ENTERPRISE in .env."
    )


def _infer_plan_from_price_id(price_id: str | None) -> str | None:
    """Return the plan name that corresponds to *price_id*, or None if unknown.

    Used as a robust fallback when session metadata does not carry the plan
    (e.g. metadata not stored or SDK serialisation quirk).
    """
    if not price_id:
        return None
    for plan_name, settings_attr in _PLAN_PRICE_MAP.items():
        configured = getattr(settings, settings_attr, None)
        if configured and configured == price_id:
            return plan_name
    # Legacy single-price fallback → treat as basic
    if settings.STRIPE_PRICE_ID and settings.STRIPE_PRICE_ID == price_id:
        return "basic"
    return None


# Ordering used to distinguish upgrades from downgrades.
PLAN_RANK: dict[str, int] = {"basic": 1, "premium": 2, "enterprise": 3}


def is_downgrade(current_plan: str | None, new_plan: str) -> bool:
    """Return True when *new_plan* is lower-tier than *current_plan*."""
    return PLAN_RANK.get(new_plan, 0) < PLAN_RANK.get(current_plan or "", 0)


def _meta_get(metadata, key: str) -> str | None:
    """Safely read *key* from a Stripe metadata object or plain dict.

    In Stripe SDK v10+, StripeObject exposes metadata fields as *attributes*
    (``metadata.plan``) rather than as dict keys.  Plain Python dicts (used in
    tests and in the webhook path) still require ``.get()``.  This helper tries
    attribute access first so both cases work correctly.
    """
    # Attribute access — works for StripeObject in SDK v10+
    val = getattr(metadata, key, None)
    if val is not None:
        return val
    # Dict-style access — works for plain dicts (tests, some webhook payloads)
    if hasattr(metadata, "get"):
        return metadata.get(key)
    return None


async def create_checkout_session(
    tenant: Tenant, user: User, db: AsyncSession, plan: str = "basic"
) -> str:
    """Create a Stripe Checkout session for *plan* and return the redirect URL."""
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured.")

    price_id = _resolve_price_id(plan)
    customer_id = await get_or_create_stripe_customer(tenant, user, db)
    client = _get_stripe_client()

    session = client.checkout.sessions.create(
        params={
            "customer": customer_id,
            "payment_method_types": ["card"],
            "line_items": [
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            "mode": "subscription",
            "success_url": f"{settings.APP_BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{settings.APP_BASE_URL}/billing/cancel",
            "metadata": {
                "tenant_id": str(tenant.id),
                "user_id": str(user.id),
                "plan": plan,
            },
        }
    )
    return session.url


async def create_upgrade_checkout_session(
    tenant: Tenant,
    user: User,
    new_plan: str,
    db: AsyncSession,
) -> str:
    """Create a Stripe Checkout session to upgrade to *new_plan*.

    A one-time coupon is applied for the unused value of the current plan so
    the user sees (and pays) only the prorated difference on the Stripe-hosted
    checkout page.  On success, the old subscription is cancelled.
    """
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured.")
    if not tenant.stripe_customer_id:
        raise RuntimeError("Tenant has no Stripe customer ID.")

    client = _get_stripe_client()

    # Locate the current active subscription
    old_subscription_id: str | None = tenant.stripe_subscription_id
    if not old_subscription_id:
        subs = client.subscriptions.list(
            params={
                "customer": tenant.stripe_customer_id,
                "status": "active",
                "limit": 1,
            }
        )
        if subs.data:
            old_subscription_id = subs.data[0].id

    price_id = _resolve_price_id(new_plan)
    customer_id = await get_or_create_stripe_customer(tenant, user, db)

    # ── Calculate the credit for the unused portion of the current plan ────────
    # We retrieve the preview invoice for an in-place update, then sum up all
    # negative lines (= the credit Stripe would give back for the old plan).
    # That credit becomes a one-time coupon on the new Checkout so the user
    # sees the real net amount instead of the full plan price.
    coupon_id: str | None = None
    currency = "eur"
    if old_subscription_id:
        try:
            sub = client.subscriptions.retrieve(old_subscription_id)
            item_id = sub.items.data[0].id
            preview = client.invoices.create_preview(
                params={
                    "customer": tenant.stripe_customer_id,
                    "subscription": old_subscription_id,
                    "subscription_details": {
                        "items": [{"id": item_id, "price": price_id}],
                        "proration_behavior": "always_invoice",
                    },
                }
            )
            currency = getattr(preview, "currency", "eur") or "eur"
            # Sum negative lines = credit for unused old plan
            credit_cents = sum(
                abs(getattr(line, "amount", 0) or 0)
                for line in getattr(getattr(preview, "lines", None), "data", [])
                if (getattr(line, "amount", 0) or 0) < 0
            )
            if credit_cents > 0:
                import time as _time

                coupon = client.coupons.create(
                    params={
                        "amount_off": credit_cents,
                        "currency": currency,
                        "duration": "once",
                        "max_redemptions": 1,
                        "redeem_by": int(_time.time()) + 7200,  # 2-hour window
                        "name": "Crédito plan anterior",
                    }
                )
                coupon_id = coupon.id
                logger.info(
                    "Upgrade coupon %s created for tenant %s (credit %d %s).",
                    coupon_id,
                    tenant.id,
                    credit_cents,
                    currency.upper(),
                )
        except Exception as exc:
            logger.warning(
                "Could not calculate upgrade proration for tenant %s: %s — proceeding without coupon.",
                tenant.id,
                exc,
            )

    metadata: dict[str, str] = {
        "tenant_id": str(tenant.id),
        "user_id": str(user.id),
        "plan": new_plan,
        "action": "upgrade",
    }
    if old_subscription_id:
        metadata["old_subscription_id"] = old_subscription_id
    if coupon_id:
        metadata["proration_coupon_id"] = coupon_id

    session_params: dict = {
        "customer": customer_id,
        "payment_method_types": ["card"],
        "line_items": [{"price": price_id, "quantity": 1}],
        "mode": "subscription",
        "success_url": f"{settings.APP_BASE_URL}/billing/success?session_id={{CHECKOUT_SESSION_ID}}",
        "cancel_url": f"{settings.APP_BASE_URL}/billing/cancel",
        "metadata": metadata,
    }
    if coupon_id:
        session_params["discounts"] = [{"coupon": coupon_id}]

    session = client.checkout.sessions.create(params=session_params)
    return session.url


async def schedule_downgrade(
    tenant: Tenant,
    new_plan: str,
    db: AsyncSession,
) -> None:
    """Schedule a plan downgrade to take effect at the next billing cycle.

    Instead of creating a new Stripe Checkout (which would prorate and refund),
    the existing subscription's price is updated with ``proration_behavior='none'``.
    Stripe will charge the new (lower) price from the next renewal onwards.
    The tenant keeps full access to the current (higher) plan until then.
    """
    if not _stripe_configured():
        raise RuntimeError("Stripe is not configured.")

    client = _get_stripe_client()

    sub_id = tenant.stripe_subscription_id
    if not sub_id:
        subs = client.subscriptions.list(
            params={
                "customer": tenant.stripe_customer_id,
                "status": "active",
                "limit": 1,
            }
        )
        if subs.data:
            sub_id = subs.data[0].id

    if not sub_id:
        raise RuntimeError("No active subscription found for tenant.")

    new_price_id = _resolve_price_id(new_plan)
    sub = client.subscriptions.retrieve(sub_id)
    item_id = sub.items.data[0].id

    client.subscriptions.update(
        sub_id,
        params={
            "items": [{"id": item_id, "price": new_price_id}],
            "proration_behavior": "none",
        },
    )

    tenant.pending_plan = new_plan
    await db.commit()
    logger.info(
        "Downgrade scheduled for tenant %s: %s → %s (takes effect at renewal).",
        tenant.id,
        tenant.plan,
        new_plan,
    )


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


async def fulfill_checkout_session(
    session_id: str,
    db: AsyncSession,
) -> bool:
    """Idempotently activate the tenant for a completed Stripe Checkout session.

    Called from /billing/success as a safety net in case the webhook has not
    yet been delivered.  Returns True if the tenant was activated (or was
    already active), False if the session is not yet paid.
    """
    if not _stripe_configured():
        return False

    client = _get_stripe_client()
    session = client.checkout.sessions.retrieve(session_id)

    if getattr(session, "payment_status", None) != "paid":
        return False

    customer_id = getattr(session, "customer", None)
    if not customer_id:
        return False

    tenant = await _get_tenant_by_customer_id(customer_id, db)
    if not tenant:
        logger.warning(
            "fulfill_checkout_session: no tenant for customer %s", customer_id
        )
        return False

    # Read plan from session metadata.
    # In Stripe SDK v10+, StripeObject exposes fields as *attributes*, not dict keys.
    # _meta_get() tries getattr first so both StripeObject and plain dicts work.
    metadata = getattr(session, "metadata", None) or {}
    plan = _meta_get(metadata, "plan")
    logger.info(
        "fulfill_checkout_session: session metadata=%r plan_from_metadata=%r",
        metadata,
        plan,
    )

    subscription_id = getattr(session, "subscription", None)

    # Retrieve the subscription once — used both for plan inference (when metadata
    # is missing/wrong) and for persisting the period_end date.
    retrieved_sub = None
    if subscription_id:
        try:
            retrieved_sub = client.subscriptions.retrieve(subscription_id)
        except Exception as exc:
            logger.warning(
                "fulfill_checkout_session: could not retrieve subscription %s: %s",
                subscription_id,
                exc,
            )

    # If metadata doesn't carry a valid plan, infer it from the subscription's price.
    if plan not in ("basic", "premium", "enterprise") and retrieved_sub:
        try:
            price_id = retrieved_sub.items.data[0].price.id
            inferred = _infer_plan_from_price_id(price_id)
            if inferred:
                logger.info(
                    "fulfill_checkout_session: inferred plan=%r from price_id=%r",
                    inferred,
                    price_id,
                )
                plan = inferred
        except Exception as exc:
            logger.warning(
                "fulfill_checkout_session: could not infer plan from subscription price: %s",
                exc,
            )

    if plan in ("basic", "premium", "enterprise"):
        tenant.plan = plan
    elif not tenant.plan:
        tenant.plan = "basic"

    if subscription_id:
        tenant.stripe_subscription_id = subscription_id

    # Persist subscription_ends_at from the retrieved subscription.
    if retrieved_sub:
        period_end = getattr(retrieved_sub, "current_period_end", None)
        if period_end is None:
            try:
                period_end = retrieved_sub.items.data[0].current_period_end
            except (AttributeError, IndexError, TypeError):
                period_end = None
        if period_end:
            tenant.subscription_ends_at = datetime.fromtimestamp(period_end, tz=UTC)

    tenant.subscription_status = "active"

    # Commit everything in a single transaction.
    await db.commit()
    logger.info(
        "fulfill_checkout_session: tenant %s activated (plan=%s) via success-page fallback.",
        tenant.id,
        tenant.plan,
    )

    # If this was a plan upgrade, cancel the old subscription AFTER committing.
    action = _meta_get(metadata, "action")
    old_sub_id = _meta_get(metadata, "old_subscription_id")
    if action == "upgrade" and old_sub_id and old_sub_id != subscription_id:
        try:
            client.subscriptions.cancel(old_sub_id)
            logger.info(
                "fulfill_checkout_session: cancelled old subscription %s for tenant %s after upgrade.",
                old_sub_id,
                tenant.id,
            )
        except Exception as exc:
            logger.warning(
                "fulfill_checkout_session: could not cancel old subscription %s: %s",
                old_sub_id,
                exc,
            )
    return True


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

    # Read plan from session metadata using _meta_get so that StripeObject
    # (attribute access) and plain dicts (dict.get) both work correctly.
    metadata = getattr(data_object, "metadata", None) or {}
    plan = _meta_get(metadata, "plan")
    logger.info(
        "_handle_checkout_completed: metadata=%r plan_from_metadata=%r",
        metadata,
        plan,
    )

    # If metadata doesn't carry a valid plan, infer it from the subscription price.
    if plan not in ("basic", "premium", "enterprise") and subscription_id:
        try:
            _sub_for_plan = _get_stripe_client().subscriptions.retrieve(subscription_id)
            price_id = _sub_for_plan.items.data[0].price.id
            inferred = _infer_plan_from_price_id(price_id)
            if inferred:
                logger.info(
                    "_handle_checkout_completed: inferred plan=%r from price_id=%r",
                    inferred,
                    price_id,
                )
                plan = inferred
        except Exception as exc:
            logger.warning(
                "_handle_checkout_completed: could not infer plan from subscription price: %s",
                exc,
            )

    if plan in ("basic", "premium", "enterprise"):
        tenant.plan = plan
    elif not getattr(tenant, "plan", None):
        tenant.plan = "basic"  # safe default

    tenant.subscription_status = "active"

    # Commit plan/status/sub_id NOW before any Stripe API calls that could throw.
    await db.commit()
    logger.info("Tenant %s activated subscription (plan=%s).", tenant.id, tenant.plan)

    # Fetch subscription period end (non-critical).
    if subscription_id:
        try:
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
                await db.commit()
        except Exception as exc:
            logger.warning(
                "_handle_checkout_completed: could not retrieve subscription period end for %s: %s",
                subscription_id,
                exc,
            )
    # (fulfill_checkout_session on the success page also does this, but the webhook
    # path is the reliable one in case the user closes the browser before landing.)
    action = _meta_get(metadata, "action")
    old_sub_id = _meta_get(metadata, "old_subscription_id")
    if action == "upgrade" and old_sub_id and old_sub_id != subscription_id:
        try:
            _get_stripe_client().subscriptions.cancel(old_sub_id)
            logger.info(
                "_handle_checkout_completed: cancelled old subscription %s for tenant %s.",
                old_sub_id,
                tenant.id,
            )
        except Exception as exc:
            logger.warning(
                "_handle_checkout_completed: could not cancel old subscription %s: %s",
                old_sub_id,
                exc,
            )

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

    # On renewal: apply a scheduled downgrade (pending_plan) or detect plan
    # from the invoice price so it stays in sync even without metadata.
    billing_reason = getattr(data_object, "billing_reason", None)
    if billing_reason == "subscription_cycle":
        if tenant.pending_plan:
            logger.info(
                "Applying scheduled downgrade for tenant %s: %s → %s.",
                tenant.id,
                tenant.plan,
                tenant.pending_plan,
            )
            tenant.plan = tenant.pending_plan
            tenant.pending_plan = None
        else:
            # Keep plan in sync with actual subscription price (safety net).
            try:
                price_id = lines_data[0].price.id if lines_data else None
                inferred = _infer_plan_from_price_id(price_id)
                if inferred and inferred != tenant.plan:
                    logger.info(
                        "Plan sync at renewal for tenant %s: %s → %s (price %s).",
                        tenant.id,
                        tenant.plan,
                        inferred,
                        price_id,
                    )
                    tenant.plan = inferred
            except Exception as exc:
                logger.warning(
                    "Could not infer plan from renewal invoice for tenant %s: %s",
                    tenant.id,
                    exc,
                )

    await db.commit()
    logger.info("Tenant %s subscription renewed (plan=%s).", tenant.id, tenant.plan)

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
                "[billing] Could not send payment-failed email to %s: %s",
                owner_email,
                exc,
            )


async def _handle_subscription_updated(data_object, db: AsyncSession) -> None:
    customer_id = data_object.customer
    if not customer_id:
        return

    tenant = await _get_tenant_by_customer_id(customer_id, db)
    if not tenant:
        return

    # Ignore updates for subscriptions that are no longer the tenant's current one.
    # This fires when the old subscription is cancelled during an upgrade.
    updated_sub_id = getattr(data_object, "id", None)
    if (
        updated_sub_id
        and tenant.stripe_subscription_id
        and updated_sub_id != tenant.stripe_subscription_id
    ):
        logger.info(
            "customer.subscription.updated: sub %s for tenant %s is not current (%s) — skipping.",
            updated_sub_id,
            tenant.id,
            tenant.stripe_subscription_id,
        )
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

    # Ignore deletions of a subscription that is no longer the tenant's current one.
    # This happens after an upgrade: we cancel the old sub, Stripe fires this event,
    # but the tenant already has the new subscription committed to DB.
    deleted_sub_id = getattr(data_object, "id", None)
    if (
        deleted_sub_id
        and tenant.stripe_subscription_id
        and deleted_sub_id != tenant.stripe_subscription_id
    ):
        logger.info(
            "customer.subscription.deleted: sub %s for tenant %s is not current (%s) — skipping.",
            deleted_sub_id,
            tenant.id,
            tenant.stripe_subscription_id,
        )
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
                "[billing] Could not send cancellation email to %s: %s",
                owner_email,
                exc,
            )

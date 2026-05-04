"""Unit tests for app.services.billing_service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import stripe

from app.services import billing_service


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_user(**kwargs) -> SimpleNamespace:
    defaults = dict(
        id=1,
        email="test@example.com",
        first_name="Test",
        last_name="User",
        role="user",
        subscription_status="trialing",
        stripe_customer_id=None,
        stripe_subscription_id=None,
        trial_ends_at=None,
        subscription_ends_at=None,
        plan=None,
        pending_plan=None,
    )
    defaults.update(kwargs)
    obj = SimpleNamespace(**defaults)
    # Tests use the same object as both user and tenant so is_subscription_blocked works.
    obj.active_tenant = obj
    return obj


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    db.execute = AsyncMock()
    return db


# ── start_trial ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_trial_sets_status_and_dates(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.TRIAL_DAYS", 14)

    user = _make_user()
    db = _fake_db()

    await billing_service.start_trial(user, db)

    assert user.subscription_status == "trialing"
    assert user.trial_ends_at is not None
    # trial_ends_at should be approximately now + 14 days
    expected = datetime.now(UTC) + timedelta(days=14)
    diff = abs((user.trial_ends_at - expected).total_seconds())
    assert diff < 5  # within 5 seconds
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_start_trial_respects_trial_days_setting(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.TRIAL_DAYS", 30)

    user = _make_user()
    db = _fake_db()

    await billing_service.start_trial(user, db)

    expected = datetime.now(UTC) + timedelta(days=30)
    diff = abs((user.trial_ends_at - expected).total_seconds())
    assert diff < 5


# ── _stripe_configured ─────────────────────────────────────────────────────────


def test_stripe_not_configured_when_key_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", None)
    assert billing_service._stripe_configured() is False


def test_stripe_configured_when_key_present(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    assert billing_service._stripe_configured() is True


# ── get_or_create_stripe_customer ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_or_create_returns_existing_customer_id(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    user = _make_user(stripe_customer_id="cus_existing")
    db = _fake_db()

    cid = await billing_service.get_or_create_stripe_customer(user, user, db)

    assert cid == "cus_existing"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_raises_when_stripe_not_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", None)
    user = _make_user()
    db = _fake_db()

    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        await billing_service.get_or_create_stripe_customer(user, user, db)


@pytest.mark.asyncio
async def test_get_or_create_creates_new_customer(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")

    fake_customer = SimpleNamespace(id="cus_new123")
    mock_client = MagicMock()
    mock_client.customers.create.return_value = fake_customer
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    user = _make_user()
    db = _fake_db()

    cid = await billing_service.get_or_create_stripe_customer(user, user, db)

    assert cid == "cus_new123"
    assert user.stripe_customer_id == "cus_new123"
    db.commit.assert_awaited_once()


# ── create_checkout_session ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_checkout_raises_when_stripe_not_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", None)
    user = _make_user(stripe_customer_id="cus_abc")
    db = _fake_db()

    with pytest.raises(RuntimeError, match="Stripe is not configured"):
        await billing_service.create_checkout_session(user, user, db)


@pytest.mark.asyncio
async def test_create_checkout_raises_when_price_id_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID", None)
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_BASIC", None)
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_PREMIUM", None)
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_ENTERPRISE", None)
    user = _make_user(stripe_customer_id="cus_abc")
    db = _fake_db()

    with pytest.raises(RuntimeError, match="STRIPE_PRICE_ID"):
        await billing_service.create_checkout_session(user, user, db)


@pytest.mark.asyncio
async def test_create_checkout_session_returns_url(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID", "price_123")
    monkeypatch.setattr("app.config.settings.APP_BASE_URL", "https://example.com")

    fake_session = SimpleNamespace(url="https://checkout.stripe.com/pay/xyz")
    mock_client = MagicMock()
    mock_client.checkout.sessions.create.return_value = fake_session
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    # Patch get_or_create to avoid another Stripe call
    async def _fake_get_or_create(tenant, user, db):
        return "cus_existing"

    monkeypatch.setattr(
        billing_service, "get_or_create_stripe_customer", _fake_get_or_create
    )

    user = _make_user()
    db = _fake_db()

    url = await billing_service.create_checkout_session(user, user, db)

    assert url == "https://checkout.stripe.com/pay/xyz"


# ── _resolve_price_id ─────────────────────────────────────────────────────────


def test_resolve_price_id_basic(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_BASIC", "price_basic_111")
    assert billing_service._resolve_price_id("basic") == "price_basic_111"


def test_resolve_price_id_premium(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_PREMIUM", "price_prem_222")
    assert billing_service._resolve_price_id("premium") == "price_prem_222"


def test_resolve_price_id_enterprise(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.config.settings.STRIPE_PRICE_ID_ENTERPRISE", "price_ent_333"
    )
    assert billing_service._resolve_price_id("enterprise") == "price_ent_333"


def test_resolve_price_id_falls_back_to_legacy(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_BASIC", None)
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID", "price_legacy_000")
    assert billing_service._resolve_price_id("basic") == "price_legacy_000"


def test_resolve_price_id_raises_when_nothing_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_BASIC", None)
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_PREMIUM", None)
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_ENTERPRISE", None)
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID", None)
    with pytest.raises(RuntimeError, match="No Stripe Price ID configured"):
        billing_service._resolve_price_id("basic")


@pytest.mark.asyncio
async def test_create_checkout_session_uses_plan_price_id(monkeypatch) -> None:
    """create_checkout_session passes the correct price_id and plan metadata."""
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_PREMIUM", "price_prem_456")
    monkeypatch.setattr("app.config.settings.APP_BASE_URL", "https://example.com")

    fake_session = SimpleNamespace(url="https://checkout.stripe.com/pay/prem")
    mock_client = MagicMock()
    mock_client.checkout.sessions.create.return_value = fake_session
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    async def _fake_get_or_create(tenant, user, db):
        return "cus_existing"

    monkeypatch.setattr(
        billing_service, "get_or_create_stripe_customer", _fake_get_or_create
    )

    user = _make_user()
    db = _fake_db()

    url = await billing_service.create_checkout_session(user, user, db, plan="premium")

    assert url == "https://checkout.stripe.com/pay/prem"
    params = mock_client.checkout.sessions.create.call_args[1]["params"]
    assert params["line_items"][0]["price"] == "price_prem_456"
    assert params["metadata"]["plan"] == "premium"


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed_sets_plan_from_metadata(
    monkeypatch,
) -> None:
    """checkout.session.completed with plan=premium in metadata → tenant.plan='premium'."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="trialing")
    user.plan = None

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                subscription=None,
                metadata={"plan": "premium"},
            )
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_activated_email",
            new=AsyncMock(),
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.plan == "premium"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed_defaults_plan_to_basic(
    monkeypatch,
) -> None:
    """checkout.session.completed with empty metadata → tenant.plan defaults to 'basic'."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="trialing")
    user.plan = None

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                subscription=None,
                metadata={},
            )
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_activated_email",
            new=AsyncMock(),
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.plan == "basic"
    db.commit.assert_awaited_once()


# ── handle_webhook ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_webhook_raises_when_secret_not_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", None)
    db = _fake_db()

    with pytest.raises(RuntimeError, match="STRIPE_WEBHOOK_SECRET"):
        await billing_service.handle_webhook(b"payload", "sig", db)


@pytest.mark.asyncio
async def test_handle_webhook_propagates_signature_error(monkeypatch) -> None:
    import stripe

    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    with patch(
        "stripe.Webhook.construct_event",
        side_effect=stripe.SignatureVerificationError("bad", "sig"),
    ):
        db = _fake_db()
        with pytest.raises(stripe.SignatureVerificationError):
            await billing_service.handle_webhook(b"payload", "bad_sig", db)


@pytest.mark.asyncio
async def test_handle_webhook_invoice_paid_updates_status(monkeypatch) -> None:
    """invoice.paid with billing_reason=subscription_create: no renewal email sent."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    # The user that will be returned from the DB lookup
    user = _make_user(stripe_customer_id="cus_abc", subscription_status="past_due")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=365)).timestamp())
    fake_event = {
        "type": "invoice.paid",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                billing_reason="subscription_create",
                lines=SimpleNamespace(
                    data=[
                        SimpleNamespace(period=SimpleNamespace(end=future_ts)),
                    ]
                ),
            )
        },
    }

    mock_send = AsyncMock()
    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_renewed_email",
            new=mock_send,
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.subscription_ends_at is not None
    db.commit.assert_awaited_once()
    mock_send.assert_not_awaited()  # no email on first invoice


@pytest.mark.asyncio
async def test_handle_webhook_invoice_paid_cycle_sends_renewal_email(
    monkeypatch,
) -> None:
    """invoice.paid with billing_reason=subscription_cycle: renewal email IS sent."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="active")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=365)).timestamp())
    fake_event = {
        "type": "invoice.paid",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                billing_reason="subscription_cycle",
                lines=SimpleNamespace(
                    data=[
                        SimpleNamespace(period=SimpleNamespace(end=future_ts)),
                    ]
                ),
            )
        },
    }

    mock_send = AsyncMock()
    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_renewed_email",
            new=mock_send,
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_deleted_cancels(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_del", subscription_status="active")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "customer.subscription.deleted",
        "data": {"object": SimpleNamespace(customer="cus_del")},
    }

    mock_send = AsyncMock()
    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_canceled_email",
            new=mock_send,
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "canceled"
    db.commit.assert_awaited_once()
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_active(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_upd", subscription_status="past_due")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=365)).timestamp())
    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_upd",
                status="active",
                cancel_at_period_end=False,
                current_period_end=future_ts,
                items=SimpleNamespace(
                    data=[SimpleNamespace(current_period_end=future_ts)]
                ),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.subscription_ends_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_cancel_at_period_end(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_cancel", subscription_status="active")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_cancel",
                status="active",
                cancel_at_period_end=True,
                canceled_at=future_ts,
                current_period_end=future_ts,
                items=SimpleNamespace(
                    data=[SimpleNamespace(current_period_end=future_ts)]
                ),
            )
        },
    }

    mock_send = AsyncMock()
    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_canceled_email",
            new=mock_send,
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    # Still active until period ends
    assert user.subscription_status == "active"
    db.commit.assert_awaited_once()
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_cancel_at_period_end_without_canceled_at(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_cancel2", subscription_status="active")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=30)).timestamp())
    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_cancel2",
                status="active",
                cancel_at_period_end=True,
                canceled_at=None,
                current_period_end=future_ts,
                items=SimpleNamespace(
                    data=[SimpleNamespace(current_period_end=future_ts)]
                ),
            )
        },
    }

    mock_send = AsyncMock()
    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_canceled_email",
            new=mock_send,
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    db.commit.assert_awaited_once()
    mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_past_due(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_pd", subscription_status="active")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_pd",
                status="past_due",
                cancel_at_period_end=False,
                current_period_end=None,
                items=SimpleNamespace(data=[]),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "past_due"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_no_customer(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    db = _fake_db()

    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer=None,
                status="active",
                cancel_at_period_end=False,
                current_period_end=None,
                items=SimpleNamespace(data=[]),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_user_not_found(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([]))

    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_unknown",
                status="active",
                cancel_at_period_end=False,
                current_period_end=None,
                items=SimpleNamespace(data=[]),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed_no_customer(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    db = _fake_db()

    fake_event = {
        "type": "checkout.session.completed",
        "data": {"object": SimpleNamespace(customer=None, subscription=None)},
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed_user_not_found(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([]))

    fake_event = {
        "type": "checkout.session.completed",
        "data": {"object": SimpleNamespace(customer="cus_gone", subscription=None)},
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_invoice_paid_no_customer(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    db = _fake_db()

    fake_event = {
        "type": "invoice.paid",
        "data": {
            "object": SimpleNamespace(customer=None, lines=SimpleNamespace(data=[]))
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_invoice_payment_failed_updates_past_due(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_fail", subscription_status="active")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "invoice.payment_failed",
        "data": {"object": SimpleNamespace(customer="cus_fail")},
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_payment_failed_email", new=AsyncMock()
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "past_due"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_invoice_payment_failed_no_customer(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    db = _fake_db()

    fake_event = {
        "type": "invoice.payment_failed",
        "data": {"object": SimpleNamespace(customer=None)},
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_canceled_status(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_c", subscription_status="active")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_c",
                status="unpaid",
                cancel_at_period_end=False,
                current_period_end=None,
                items=SimpleNamespace(data=[]),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "canceled"
    db.commit.assert_awaited_once()


# ── require_subscription (auth.py logic) ──────────────────────────────────────


# ── create_portal_session ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_portal_session_raises_when_stripe_not_configured(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", None)
    user = _make_user(stripe_customer_id="cus_abc")

    with pytest.raises(RuntimeError, match="Stripe is not configured"):
        await billing_service.create_portal_session(user)


@pytest.mark.asyncio
async def test_create_portal_session_raises_when_no_customer_id(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    user = _make_user(stripe_customer_id=None)

    with pytest.raises(RuntimeError, match="no Stripe customer ID"):
        await billing_service.create_portal_session(user)


@pytest.mark.asyncio
async def test_create_portal_session_returns_url(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr("app.config.settings.APP_BASE_URL", "https://example.com")

    fake_session = SimpleNamespace(url="https://billing.stripe.com/session/xyz")
    mock_client = MagicMock()
    mock_client.billing_portal.sessions.create.return_value = fake_session
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    user = _make_user(stripe_customer_id="cus_abc")

    url = await billing_service.create_portal_session(user)

    assert url == "https://billing.stripe.com/session/xyz"
    mock_client.billing_portal.sessions.create.assert_called_once()


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed_no_subscription_id(
    monkeypatch,
) -> None:
    """User found but no subscription_id — skip Stripe retrieval, still activate."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="trialing")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                subscription=None,
            )
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_activated_email",
            new=AsyncMock(),
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed_subscription_items_fallback_fails(
    monkeypatch,
) -> None:
    """sub.items.data[0] raises → period_end stays None, user still activated."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="trialing")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    # current_period_end is None AND items.data is empty → IndexError on fallback
    fake_sub = SimpleNamespace(
        current_period_end=None,
        items=SimpleNamespace(data=[]),
    )
    mock_client = MagicMock()
    mock_client.subscriptions.retrieve.return_value = fake_sub
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                subscription="sub_789",
            )
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_activated_email",
            new=AsyncMock(),
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.subscription_ends_at is None
    db.commit.assert_awaited_once()


# ── checkout.session.completed with subscription_id ───────────────────────────


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed_with_subscription_id(
    monkeypatch,
) -> None:
    """When checkout has a subscription_id, we retrieve it from Stripe to get period_end."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="trialing")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=365)).timestamp())
    fake_sub = SimpleNamespace(
        current_period_end=future_ts, items=SimpleNamespace(data=[])
    )
    mock_client = MagicMock()
    mock_client.subscriptions.retrieve.return_value = fake_sub
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                subscription="sub_123",
            )
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_activated_email",
            new=AsyncMock(),
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.subscription_ends_at is not None
    # commit is called at least twice: once for plan/status, once for period_end
    assert db.commit.await_count >= 2


@pytest.mark.asyncio
async def test_handle_webhook_checkout_completed_period_end_from_items(
    monkeypatch,
) -> None:
    """Fallback: period_end comes from sub.items.data[0] when current_period_end is None."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="trialing")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=365)).timestamp())
    fake_sub = SimpleNamespace(
        current_period_end=None,
        items=SimpleNamespace(data=[SimpleNamespace(current_period_end=future_ts)]),
    )
    mock_client = MagicMock()
    mock_client.subscriptions.retrieve.return_value = fake_sub
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    fake_event = {
        "type": "checkout.session.completed",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                subscription="sub_456",
            )
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_activated_email",
            new=AsyncMock(),
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.subscription_ends_at is not None


@pytest.mark.asyncio
async def test_handle_webhook_invoice_payment_failed_user_not_found(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([]))

    fake_event = {
        "type": "invoice.payment_failed",
        "data": {"object": SimpleNamespace(customer="cus_gone")},
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_invoice_paid_skips_line_without_period_end(
    monkeypatch,
) -> None:
    """Loop iterates past a line with no period.end before finding one with it."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="past_due")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=365)).timestamp())
    fake_event = {
        "type": "invoice.paid",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                lines=SimpleNamespace(
                    data=[
                        # First line: no usable period.end — loop continues
                        SimpleNamespace(period=SimpleNamespace(end=None)),
                        # Second line: has period.end — loop breaks
                        SimpleNamespace(period=SimpleNamespace(end=future_ts)),
                    ]
                ),
            )
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_renewed_email",
            new=AsyncMock(),
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.subscription_ends_at is not None
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_unrecognized_status(
    monkeypatch,
) -> None:
    """stripe_status not in known set → no status change, still commits."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_tri", subscription_status="trialing")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_tri",
                status="trialing",  # not in the handled set
                cancel_at_period_end=False,
                current_period_end=None,
                items=SimpleNamespace(data=[]),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    # Status unchanged — none of the elif branches matched
    assert user.subscription_status == "trialing"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_incomplete_expired_status(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_ie", subscription_status="active")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_ie",
                status="incomplete_expired",
                cancel_at_period_end=False,
                current_period_end=None,
                items=SimpleNamespace(data=[]),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "canceled"
    db.commit.assert_awaited_once()


# ── invoice.paid edge cases ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_webhook_invoice_paid_user_not_found(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([]))

    fake_event = {
        "type": "invoice.paid",
        "data": {
            "object": SimpleNamespace(
                customer="cus_gone",
                lines=SimpleNamespace(data=[]),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_invoice_paid_no_period_end(monkeypatch) -> None:
    """invoice.paid with lines that have no usable period — still sets active, no ends_at."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_abc", subscription_status="past_due")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    fake_event = {
        "type": "invoice.paid",
        "data": {
            "object": SimpleNamespace(
                customer="cus_abc",
                lines=SimpleNamespace(data=[]),
            )
        },
    }

    with (
        patch("stripe.Webhook.construct_event", return_value=fake_event),
        patch(
            "app.services.billing_service.send_subscription_renewed_email",
            new=AsyncMock(),
        ),
    ):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.subscription_ends_at is None
    db.commit.assert_awaited_once()


# ── subscription.deleted edge cases ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_webhook_subscription_deleted_no_customer(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    db = _fake_db()

    fake_event = {
        "type": "customer.subscription.deleted",
        "data": {"object": SimpleNamespace(customer=None)},
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_handle_webhook_subscription_deleted_user_not_found(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([]))

    fake_event = {
        "type": "customer.subscription.deleted",
        "data": {"object": SimpleNamespace(customer="cus_gone")},
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


# ── unknown webhook event ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_webhook_unknown_event_type_is_noop(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    db = _fake_db()

    fake_event = {
        "type": "some.unknown.event",
        "data": {"object": SimpleNamespace()},
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    db.commit.assert_not_awaited()


# ── subscription.updated — period_end via items fallback ──────────────────────


@pytest.mark.asyncio
async def test_handle_webhook_subscription_updated_period_end_from_items(
    monkeypatch,
) -> None:
    """When current_period_end is None, the value comes from items.data[0]."""
    monkeypatch.setattr("app.config.settings.STRIPE_WEBHOOK_SECRET", "whsec_test")

    user = _make_user(stripe_customer_id="cus_upd2", subscription_status="past_due")

    from tests.conftest import result as fake_result

    db = _fake_db()
    db.execute = AsyncMock(return_value=fake_result([user]))

    future_ts = int((datetime.now(UTC) + timedelta(days=365)).timestamp())
    fake_event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": SimpleNamespace(
                customer="cus_upd2",
                status="active",
                cancel_at_period_end=False,
                current_period_end=None,
                items=SimpleNamespace(
                    data=[SimpleNamespace(current_period_end=future_ts)]
                ),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "active"
    assert user.subscription_ends_at is not None
    db.commit.assert_awaited_once()


# ── _get_stripe_client ────────────────────────────────────────────────────────


def test_get_stripe_client_uses_secret_key(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_xyz")
    client = billing_service._get_stripe_client()
    assert isinstance(client, stripe.StripeClient)


# ── require_subscription (auth.py logic) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_require_subscription_allows_active_user() -> None:
    from app.auth import require_subscription

    user = _make_user(
        role="user",
        subscription_status="active",
        subscription_ends_at=datetime.now(UTC) + timedelta(days=30),
    )
    result = await require_subscription(user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_subscription_allows_trialing_user() -> None:
    from app.auth import require_subscription, SubscriptionRequiredException

    user = _make_user(
        role="user",
        subscription_status="trialing",
        trial_ends_at=datetime.now(UTC) + timedelta(days=7),
    )
    result = await require_subscription(user=user)
    assert result is user


@pytest.mark.asyncio
async def test_require_subscription_does_not_block_expired_trial() -> None:
    """require_subscription no longer blocks — read_only gating is in plan_access."""
    from app.auth import require_subscription
    from app.plan_access import is_read_only

    user = _make_user(
        role="user",
        subscription_status="trialing",
        trial_ends_at=datetime.now(UTC) - timedelta(days=1),
    )
    result = await require_subscription(user=user)
    assert result is user
    assert is_read_only(user) is True


@pytest.mark.asyncio
async def test_require_subscription_does_not_block_canceled() -> None:
    """require_subscription no longer blocks — read_only gating is in plan_access."""
    from app.auth import require_subscription
    from app.plan_access import is_read_only

    user = _make_user(role="user", subscription_status="canceled")
    result = await require_subscription(user=user)
    assert result is user
    assert is_read_only(user) is True


@pytest.mark.asyncio
async def test_require_subscription_admin_always_allowed() -> None:
    from app.auth import require_subscription

    user = _make_user(role="admin", subscription_status="canceled", trial_ends_at=None)
    result = await require_subscription(user=user)
    assert result is user


# ── create_upgrade_checkout_session ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_upgrade_checkout_session_raises_when_stripe_not_configured(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", None)
    tenant = _make_user(
        stripe_customer_id="cus_abc", subscription_status="active", plan="basic"
    )
    user = _make_user()
    db = _fake_db()

    with pytest.raises(RuntimeError, match="Stripe is not configured"):
        await billing_service.create_upgrade_checkout_session(
            tenant, user, "premium", db
        )


@pytest.mark.asyncio
async def test_create_upgrade_checkout_session_raises_when_no_customer_id(
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    tenant = _make_user(
        stripe_customer_id=None, subscription_status="active", plan="basic"
    )
    user = _make_user()
    db = _fake_db()

    with pytest.raises(RuntimeError, match="no Stripe customer ID"):
        await billing_service.create_upgrade_checkout_session(
            tenant, user, "premium", db
        )


@pytest.mark.asyncio
async def test_create_upgrade_checkout_session_returns_url_with_stored_subscription_id(
    monkeypatch,
) -> None:
    """Uses stored stripe_subscription_id as old_subscription_id in metadata."""
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_PREMIUM", "price_prem_456")
    monkeypatch.setattr("app.config.settings.APP_BASE_URL", "https://app.example.com")

    fake_session = SimpleNamespace(
        url="https://checkout.stripe.com/pay/cs_upgrade_test"
    )
    mock_client = MagicMock()
    mock_client.checkout.sessions.create.return_value = fake_session
    mock_client.customers.create.return_value = SimpleNamespace(id="cus_abc")
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    tenant = _make_user(
        stripe_customer_id="cus_abc",
        stripe_subscription_id="sub_basic_123",
        subscription_status="active",
        plan="basic",
    )
    user = _make_user(email="test@example.com")
    db = _fake_db()
    from tests.conftest import result as fake_result

    db.execute = AsyncMock(return_value=fake_result([tenant]))

    url = await billing_service.create_upgrade_checkout_session(
        tenant, user, "premium", db
    )

    assert url == "https://checkout.stripe.com/pay/cs_upgrade_test"
    call_params = mock_client.checkout.sessions.create.call_args[1]["params"]
    assert call_params["metadata"]["action"] == "upgrade"
    assert call_params["metadata"]["old_subscription_id"] == "sub_basic_123"
    assert call_params["metadata"]["plan"] == "premium"
    # Should NOT call subscriptions.list since ID is already stored
    mock_client.subscriptions.list.assert_not_called()


@pytest.mark.asyncio
async def test_create_upgrade_checkout_session_falls_back_to_list_for_old_sub(
    monkeypatch,
) -> None:
    """Falls back to subscriptions.list when no stripe_subscription_id stored."""
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_PREMIUM", "price_prem_456")
    monkeypatch.setattr("app.config.settings.APP_BASE_URL", "https://app.example.com")

    fake_sub = SimpleNamespace(id="sub_from_list")
    fake_session = SimpleNamespace(
        url="https://checkout.stripe.com/pay/cs_upgrade_list"
    )
    mock_client = MagicMock()
    mock_client.subscriptions.list.return_value = SimpleNamespace(data=[fake_sub])
    mock_client.checkout.sessions.create.return_value = fake_session
    mock_client.customers.create.return_value = SimpleNamespace(id="cus_abc")
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    tenant = _make_user(
        stripe_customer_id="cus_abc",
        stripe_subscription_id=None,
        subscription_status="active",
        plan="basic",
    )
    user = _make_user(email="test@example.com")
    db = _fake_db()
    from tests.conftest import result as fake_result

    db.execute = AsyncMock(return_value=fake_result([tenant]))

    url = await billing_service.create_upgrade_checkout_session(
        tenant, user, "premium", db
    )

    assert url == "https://checkout.stripe.com/pay/cs_upgrade_list"
    call_params = mock_client.checkout.sessions.create.call_args[1]["params"]
    assert call_params["metadata"]["old_subscription_id"] == "sub_from_list"
    mock_client.subscriptions.list.assert_called_once()


@pytest.mark.asyncio
async def test_create_upgrade_checkout_session_applies_proration_coupon(
    monkeypatch,
) -> None:
    """A one-time coupon equal to the unused plan credit is applied to the session."""
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID_PREMIUM", "price_prem_456")
    monkeypatch.setattr("app.config.settings.APP_BASE_URL", "https://app.example.com")

    # Preview has one negative line = 4950 cents credit for unused basic plan
    fake_line = SimpleNamespace(amount=-4950)
    fake_preview = SimpleNamespace(
        currency="eur",
        lines=SimpleNamespace(data=[fake_line]),
    )
    fake_sub = SimpleNamespace(
        items=SimpleNamespace(data=[SimpleNamespace(id="item_abc")])
    )
    fake_coupon = SimpleNamespace(id="coupon_proration_123")
    fake_session = SimpleNamespace(url="https://checkout.stripe.com/pay/cs_coupon_test")

    mock_client = MagicMock()
    mock_client.subscriptions.retrieve.return_value = fake_sub
    mock_client.invoices.create_preview.return_value = fake_preview
    mock_client.coupons.create.return_value = fake_coupon
    mock_client.checkout.sessions.create.return_value = fake_session
    mock_client.customers.create.return_value = SimpleNamespace(id="cus_abc")
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    tenant = _make_user(
        stripe_customer_id="cus_abc",
        stripe_subscription_id="sub_basic_123",
        subscription_status="active",
        plan="basic",
    )
    user = _make_user(email="test@example.com")
    db = _fake_db()
    from tests.conftest import result as fake_result

    db.execute = AsyncMock(return_value=fake_result([tenant]))

    url = await billing_service.create_upgrade_checkout_session(
        tenant, user, "premium", db
    )

    assert url == "https://checkout.stripe.com/pay/cs_coupon_test"

    # Coupon created with the credit amount
    coupon_params = mock_client.coupons.create.call_args[1]["params"]
    assert coupon_params["amount_off"] == 4950
    assert coupon_params["currency"] == "eur"
    assert coupon_params["duration"] == "once"
    assert coupon_params["max_redemptions"] == 1

    # Discount applied to checkout session
    call_params = mock_client.checkout.sessions.create.call_args[1]["params"]
    assert call_params["discounts"] == [{"coupon": "coupon_proration_123"}]
    assert call_params["metadata"]["proration_coupon_id"] == "coupon_proration_123"


# ── fulfill_checkout_session — upgrade cancels old subscription ─────────────────


@pytest.mark.asyncio
async def test_fulfill_checkout_session_cancels_old_subscription_on_upgrade(
    monkeypatch,
) -> None:
    """When metadata has action=upgrade and old_subscription_id, old sub is cancelled."""
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")

    meta = {
        "plan": "premium",
        "action": "upgrade",
        "old_subscription_id": "sub_old_basic",
        "tenant_id": "1",
    }

    class FakeMeta:
        def get(self, k, d=None):
            return meta.get(k, d)

    fake_session = SimpleNamespace(
        payment_status="paid",
        customer="cus_abc",
        subscription="sub_new_premium",
        metadata=FakeMeta(),
    )
    fake_sub = SimpleNamespace(current_period_end=1800000000)

    mock_client = MagicMock()
    mock_client.checkout.sessions.retrieve.return_value = fake_session
    mock_client.subscriptions.retrieve.return_value = fake_sub
    mock_client.subscriptions.cancel.return_value = SimpleNamespace(status="canceled")
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    tenant = _make_user(
        stripe_customer_id="cus_abc",
        stripe_subscription_id="sub_old_basic",
        plan="basic",
        subscription_status="active",
    )
    db = _fake_db()
    from tests.conftest import result as fake_result

    db.execute = AsyncMock(return_value=fake_result([tenant]))

    result = await billing_service.fulfill_checkout_session("cs_test_123", db)

    assert result is True
    assert tenant.plan == "premium"
    assert tenant.stripe_subscription_id == "sub_new_premium"
    mock_client.subscriptions.cancel.assert_called_once_with("sub_old_basic")

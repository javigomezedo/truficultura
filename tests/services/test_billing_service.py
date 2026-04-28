"""Unit tests for app.services.billing_service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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
        trial_ends_at=None,
        subscription_ends_at=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


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

    cid = await billing_service.get_or_create_stripe_customer(user, db)

    assert cid == "cus_existing"
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_raises_when_stripe_not_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", None)
    user = _make_user()
    db = _fake_db()

    with pytest.raises(RuntimeError, match="STRIPE_SECRET_KEY"):
        await billing_service.get_or_create_stripe_customer(user, db)


@pytest.mark.asyncio
async def test_get_or_create_creates_new_customer(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")

    fake_customer = SimpleNamespace(id="cus_new123")
    mock_client = MagicMock()
    mock_client.customers.create.return_value = fake_customer
    monkeypatch.setattr(billing_service, "_get_stripe_client", lambda: mock_client)

    user = _make_user()
    db = _fake_db()

    cid = await billing_service.get_or_create_stripe_customer(user, db)

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
        await billing_service.create_checkout_session(user, db)


@pytest.mark.asyncio
async def test_create_checkout_raises_when_price_id_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_abc")
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID", None)
    user = _make_user(stripe_customer_id="cus_abc")
    db = _fake_db()

    with pytest.raises(RuntimeError, match="STRIPE_PRICE_ID"):
        await billing_service.create_checkout_session(user, db)


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
    async def _fake_get_or_create(user, db):
        return "cus_existing"

    monkeypatch.setattr(
        billing_service, "get_or_create_stripe_customer", _fake_get_or_create
    )

    user = _make_user()
    db = _fake_db()

    url = await billing_service.create_checkout_session(user, db)

    assert url == "https://checkout.stripe.com/pay/xyz"


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
                lines=SimpleNamespace(
                    data=[
                        SimpleNamespace(period=SimpleNamespace(end=future_ts)),
                    ]
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

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    assert user.subscription_status == "canceled"
    db.commit.assert_awaited_once()


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
                current_period_end=future_ts,
                items=SimpleNamespace(
                    data=[SimpleNamespace(current_period_end=future_ts)]
                ),
            )
        },
    }

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
        await billing_service.handle_webhook(b"payload", "sig", db)

    # Still active until period ends
    assert user.subscription_status == "active"
    db.commit.assert_awaited_once()


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

    with patch("stripe.Webhook.construct_event", return_value=fake_event):
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
async def test_require_subscription_blocks_expired_trial() -> None:
    from app.auth import require_subscription, SubscriptionRequiredException

    user = _make_user(
        role="user",
        subscription_status="trialing",
        trial_ends_at=datetime.now(UTC) - timedelta(days=1),
    )
    with pytest.raises(SubscriptionRequiredException):
        await require_subscription(user=user)


@pytest.mark.asyncio
async def test_require_subscription_blocks_canceled() -> None:
    from app.auth import require_subscription, SubscriptionRequiredException

    user = _make_user(role="user", subscription_status="canceled")
    with pytest.raises(SubscriptionRequiredException):
        await require_subscription(user=user)


@pytest.mark.asyncio
async def test_require_subscription_admin_always_allowed() -> None:
    from app.auth import require_subscription

    user = _make_user(role="admin", subscription_status="canceled", trial_ends_at=None)
    result = await require_subscription(user=user)
    assert result is user

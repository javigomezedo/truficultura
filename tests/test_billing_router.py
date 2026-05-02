"""Tests for app.routers.billing."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import stripe
from fastapi.testclient import TestClient

from app.auth import require_user
from app.database import get_db
from app.main import app


def _user(**kwargs):
    tenant_kwargs = {
        k: kwargs.pop(k)
        for k in list(kwargs)
        if k in ("subscription_status", "stripe_customer_id", "trial_ends_at", "subscription_ends_at")
    }
    tenant_defaults = dict(
        subscription_status="trialing",
        stripe_customer_id="cus_test",
        trial_ends_at=None,
        subscription_ends_at=None,
    )
    tenant_defaults.update(tenant_kwargs)
    tenant = SimpleNamespace(**tenant_defaults)
    defaults = dict(
        id=1,
        role="user",
        is_active=True,
        email="test@example.com",
        first_name="Test",
        last_name="User",
        active_tenant_id=1,
        active_tenant=tenant,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _db():
    db = MagicMock()
    db.commit = AsyncMock()
    return db


# ── /billing/subscribe ─────────────────────────────────────────────────────────


def test_billing_subscribe_renders(monkeypatch) -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    monkeypatch.setattr("app.config.settings.STRIPE_SECRET_KEY", "sk_test_x")
    monkeypatch.setattr("app.config.settings.STRIPE_PRICE_ID", "price_x")
    monkeypatch.setattr("app.config.settings.STRIPE_PUBLISHABLE_KEY", "pk_test_x")

    try:
        response = TestClient(app).get("/billing/subscribe")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Suscripción" in response.text


# ── /billing/checkout ─────────────────────────────────────────────────────────


def test_billing_checkout_redirects_to_stripe(monkeypatch) -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    monkeypatch.setattr(
        "app.routers.billing.billing_service.create_checkout_session",
        AsyncMock(return_value="https://checkout.stripe.com/pay/xyz"),
    )

    try:
        response = TestClient(app).post("/billing/checkout", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "https://checkout.stripe.com/pay/xyz"


def test_billing_checkout_returns_503_on_error(monkeypatch) -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    monkeypatch.setattr(
        "app.routers.billing.billing_service.create_checkout_session",
        AsyncMock(side_effect=RuntimeError("Stripe not configured")),
    )

    try:
        response = TestClient(app).post("/billing/checkout")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


# ── /billing/success ──────────────────────────────────────────────────────────


def test_billing_success_renders(monkeypatch) -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    try:
        response = TestClient(app).get("/billing/success")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


# ── /billing/cancel ───────────────────────────────────────────────────────────


def test_billing_cancel_renders(monkeypatch) -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    try:
        response = TestClient(app).get("/billing/cancel")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


# ── /billing/portal ───────────────────────────────────────────────────────────


def test_billing_portal_redirects(monkeypatch) -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    monkeypatch.setattr(
        "app.routers.billing.billing_service.create_portal_session",
        AsyncMock(return_value="https://billing.stripe.com/session/xyz"),
    )

    try:
        response = TestClient(app).post("/billing/portal", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "https://billing.stripe.com/session/xyz"


def test_billing_portal_returns_503_on_error(monkeypatch) -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    monkeypatch.setattr(
        "app.routers.billing.billing_service.create_portal_session",
        AsyncMock(side_effect=RuntimeError("No Stripe customer")),
    )

    try:
        response = TestClient(app).post("/billing/portal")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


# ── /stripe/webhook ───────────────────────────────────────────────────────────


def test_stripe_webhook_ok(monkeypatch) -> None:
    app.dependency_overrides[get_db] = lambda: _db()

    monkeypatch.setattr(
        "app.routers.billing.billing_service.handle_webhook",
        AsyncMock(return_value=None),
    )

    try:
        response = TestClient(app).post(
            "/billing/stripe/webhook",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=abc"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_stripe_webhook_invalid_signature(monkeypatch) -> None:
    app.dependency_overrides[get_db] = lambda: _db()

    monkeypatch.setattr(
        "app.routers.billing.billing_service.handle_webhook",
        AsyncMock(
            side_effect=stripe.SignatureVerificationError("bad sig", "sig_header")
        ),
    )

    try:
        response = TestClient(app).post(
            "/billing/stripe/webhook",
            content=b"{}",
            headers={"stripe-signature": "bad"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400


def test_stripe_webhook_runtime_error(monkeypatch) -> None:
    app.dependency_overrides[get_db] = lambda: _db()

    monkeypatch.setattr(
        "app.routers.billing.billing_service.handle_webhook",
        AsyncMock(side_effect=RuntimeError("STRIPE_WEBHOOK_SECRET not configured")),
    )

    try:
        response = TestClient(app).post(
            "/billing/stripe/webhook",
            content=b"{}",
            headers={"stripe-signature": "t=1,v1=abc"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503

"""Unit tests for app.plan_access — plan mode, feature gating, and write access."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.plan_access import (
    PLANT_LIMIT_BASIC,
    PlantLimitExceededException,
    PlanUpgradeRequiredException,
    WriteAccessDeniedException,
    get_plan_mode,
    has_feature,
    is_read_only,
)


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_tenant(
    *,
    subscription_status: str = "trialing",
    trial_ends_at: datetime | None = None,
    subscription_ends_at: datetime | None = None,
    plan: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        subscription_status=subscription_status,
        trial_ends_at=trial_ends_at,
        subscription_ends_at=subscription_ends_at,
        plan=plan,
    )


def _make_user(
    *,
    role: str = "user",
    tenant: SimpleNamespace | None = None,
) -> SimpleNamespace:
    user = SimpleNamespace(role=role, active_tenant=tenant)
    return user


def _future(days: int = 10) -> datetime:
    return datetime.now(UTC) + timedelta(days=days)


def _past(days: int = 1) -> datetime:
    return datetime.now(UTC) - timedelta(days=days)


# ── get_plan_mode ──────────────────────────────────────────────────────────────


def test_admin_always_enterprise() -> None:
    user = _make_user(role="admin", tenant=None)
    assert get_plan_mode(user) == "enterprise"


def test_admin_ignores_tenant_status() -> None:
    tenant = _make_tenant(subscription_status="canceled")
    user = _make_user(role="admin", tenant=tenant)
    assert get_plan_mode(user) == "enterprise"


def test_no_tenant_returns_trial() -> None:
    user = _make_user(role="user", tenant=None)
    assert get_plan_mode(user) == "trial"


def test_active_trial_returns_trial() -> None:
    tenant = _make_tenant(subscription_status="trialing", trial_ends_at=_future())
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "trial"


def test_expired_trial_returns_read_only() -> None:
    tenant = _make_tenant(subscription_status="trialing", trial_ends_at=_past())
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "read_only"


def test_trialing_no_end_date_returns_read_only() -> None:
    tenant = _make_tenant(subscription_status="trialing", trial_ends_at=None)
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "read_only"


def test_active_subscription_basic() -> None:
    tenant = _make_tenant(
        subscription_status="active",
        subscription_ends_at=_future(),
        plan="basic",
    )
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "basic"


def test_active_subscription_premium() -> None:
    tenant = _make_tenant(
        subscription_status="active",
        subscription_ends_at=_future(),
        plan="premium",
    )
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "premium"


def test_active_subscription_enterprise() -> None:
    tenant = _make_tenant(
        subscription_status="active",
        subscription_ends_at=_future(),
        plan="enterprise",
    )
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "enterprise"


def test_active_subscription_no_plan_defaults_to_basic() -> None:
    tenant = _make_tenant(
        subscription_status="active",
        subscription_ends_at=_future(),
        plan=None,
    )
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "basic"


def test_active_subscription_expired_ends_at_returns_read_only() -> None:
    tenant = _make_tenant(
        subscription_status="active",
        subscription_ends_at=_past(),
        plan="premium",
    )
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "read_only"


def test_past_due_returns_read_only() -> None:
    tenant = _make_tenant(subscription_status="past_due")
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "read_only"


def test_canceled_returns_read_only() -> None:
    tenant = _make_tenant(subscription_status="canceled")
    user = _make_user(tenant=tenant)
    assert get_plan_mode(user) == "read_only"


# ── is_read_only ───────────────────────────────────────────────────────────────


def test_is_read_only_true_when_canceled() -> None:
    tenant = _make_tenant(subscription_status="canceled")
    user = _make_user(tenant=tenant)
    assert is_read_only(user) is True


def test_is_read_only_false_when_active_basic() -> None:
    tenant = _make_tenant(
        subscription_status="active", subscription_ends_at=_future(), plan="basic"
    )
    user = _make_user(tenant=tenant)
    assert is_read_only(user) is False


def test_is_read_only_false_for_trial() -> None:
    tenant = _make_tenant(subscription_status="trialing", trial_ends_at=_future())
    user = _make_user(tenant=tenant)
    assert is_read_only(user) is False


# ── has_feature ────────────────────────────────────────────────────────────────


def _user_with_mode(mode: str) -> SimpleNamespace:
    """Return a user that resolves to the given plan mode."""
    if mode == "trial":
        tenant = _make_tenant(subscription_status="trialing", trial_ends_at=_future())
    elif mode == "read_only":
        tenant = _make_tenant(subscription_status="canceled")
    elif mode == "basic":
        tenant = _make_tenant(
            subscription_status="active", subscription_ends_at=_future(), plan="basic"
        )
    elif mode == "premium":
        tenant = _make_tenant(
            subscription_status="active", subscription_ends_at=_future(), plan="premium"
        )
    elif mode == "enterprise":
        tenant = _make_tenant(
            subscription_status="active", subscription_ends_at=_future(), plan="enterprise"
        )
    else:
        raise ValueError(mode)
    return _make_user(tenant=tenant)


# Parcelas / gastos / ingresos are available to all (feature not in _FEATURE_PLANS)
@pytest.mark.parametrize("mode", ["trial", "read_only", "basic", "premium", "enterprise"])
def test_unrestricted_feature_always_available(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "parcelas") is True


# lluvia not in _FEATURE_PLANS → available to all
@pytest.mark.parametrize("mode", ["trial", "read_only", "basic", "premium", "enterprise"])
def test_lluvia_available_to_all(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "lluvia") is True


# tiempo — premium+
@pytest.mark.parametrize("mode", ["trial", "premium", "enterprise"])
def test_tiempo_available_to_premium_plus(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "tiempo") is True


@pytest.mark.parametrize("mode", ["read_only", "basic"])
def test_tiempo_not_available_below_premium(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "tiempo") is False


# analitica_parcelas — premium+
@pytest.mark.parametrize("mode", ["trial", "premium", "enterprise"])
def test_analitica_parcelas_available_to_premium_plus(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "analitica_parcelas") is True


@pytest.mark.parametrize("mode", ["read_only", "basic"])
def test_analitica_parcelas_not_below_premium(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "analitica_parcelas") is False


# simulador_riego — premium+
@pytest.mark.parametrize("mode", ["trial", "premium", "enterprise"])
def test_simulador_riego_available_to_premium_plus(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "simulador_riego") is True


@pytest.mark.parametrize("mode", ["read_only", "basic"])
def test_simulador_riego_not_below_premium(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "simulador_riego") is False


# asistente_ia — premium+
@pytest.mark.parametrize("mode", ["trial", "premium", "enterprise"])
def test_asistente_ia_available_to_premium_plus(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "asistente_ia") is True


@pytest.mark.parametrize("mode", ["read_only", "basic"])
def test_asistente_ia_not_below_premium(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "asistente_ia") is False


# tenants — enterprise only
@pytest.mark.parametrize("mode", ["trial", "enterprise"])
def test_tenants_available_to_enterprise(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "tenants") is True


@pytest.mark.parametrize("mode", ["read_only", "basic", "premium"])
def test_tenants_not_below_enterprise(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "tenants") is False


# ── Exception classes ─────────────────────────────────────────────────────────


def test_plan_upgrade_required_exception_attributes() -> None:
    exc = PlanUpgradeRequiredException("tiempo", "premium")
    assert exc.feature == "tiempo"
    assert exc.required_plan == "premium"


def test_plant_limit_exceeded_exception_attributes() -> None:
    exc = PlantLimitExceededException(500)
    assert exc.limit == 500
    assert "500" in str(exc)
    assert "Premium" in str(exc)


def test_write_access_denied_exception_is_exception() -> None:
    exc = WriteAccessDeniedException()
    assert isinstance(exc, Exception)


def test_plant_limit_basic_constant() -> None:
    assert PLANT_LIMIT_BASIC == 500

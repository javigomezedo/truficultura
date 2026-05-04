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
            subscription_status="active",
            subscription_ends_at=_future(),
            plan="enterprise",
        )
    else:
        raise ValueError(mode)
    return _make_user(tenant=tenant)


# Parcelas / gastos / ingresos are available to all (feature not in _FEATURE_PLANS)
@pytest.mark.parametrize(
    "mode", ["trial", "read_only", "basic", "premium", "enterprise"]
)
def test_unrestricted_feature_always_available(mode: str) -> None:
    user = _user_with_mode(mode)
    assert has_feature(user, "parcelas") is True


# lluvia not in _FEATURE_PLANS → available to all
@pytest.mark.parametrize(
    "mode", ["trial", "read_only", "basic", "premium", "enterprise"]
)
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


# ── require_write_access (FastAPI dep, called directly) ───────────────────────


@pytest.mark.asyncio
async def test_require_write_access_raises_for_read_only() -> None:
    from app.plan_access import require_write_access

    user = _make_user(tenant=_make_tenant(subscription_status="canceled"))
    with pytest.raises(WriteAccessDeniedException):
        await require_write_access(user=user)


@pytest.mark.asyncio
async def test_require_write_access_passes_for_active_basic() -> None:
    from app.plan_access import require_write_access

    tenant = _make_tenant(
        subscription_status="active", subscription_ends_at=_future(), plan="basic"
    )
    user = _make_user(tenant=tenant)
    returned = await require_write_access(user=user)
    assert returned is user


# ── require_feature inner _dep (FastAPI dep factory, called directly) ─────────


@pytest.mark.asyncio
async def test_require_feature_dep_raises_when_plan_insufficient() -> None:
    from app.plan_access import require_feature

    user = _user_with_mode("basic")
    _dep = require_feature("tiempo")
    with pytest.raises(PlanUpgradeRequiredException) as exc_info:
        await _dep(user=user)
    assert exc_info.value.feature == "tiempo"
    assert exc_info.value.required_plan == "premium"


@pytest.mark.asyncio
async def test_require_feature_dep_passes_for_sufficient_plan() -> None:
    from app.plan_access import require_feature

    user = _user_with_mode("premium")
    _dep = require_feature("tiempo")
    returned = await _dep(user=user)
    assert returned is user


@pytest.mark.asyncio
async def test_require_feature_dep_raises_for_enterprise_only_feature() -> None:
    from app.plan_access import require_feature

    user = _user_with_mode("premium")
    _dep = require_feature("tenants")
    with pytest.raises(PlanUpgradeRequiredException) as exc_info:
        await _dep(user=user)
    assert exc_info.value.required_plan == "enterprise"


# ── require_plant_limit (DB-dependent dep, called directly) ───────────────────


class _FakeDB:
    """Minimal async session fake that returns pre-set results for execute()."""

    def __init__(self, *results) -> None:
        self._results = iter(results)

    async def execute(self, *args, **kwargs):
        return next(self._results)


class _FakeRow:
    def __init__(self, **kwargs) -> None:
        self.__dict__.update(kwargs)


class _FakeResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


@pytest.mark.asyncio
async def test_require_plant_limit_non_basic_skips_check() -> None:
    """Premium users bypass the plant limit check without hitting the DB."""
    from app.plan_access import require_plant_limit

    user = _user_with_mode("premium")
    db = _FakeDB()  # no execute calls should happen
    returned = await require_plant_limit(user=user, db=db)  # type: ignore[arg-type]
    assert returned is user


@pytest.mark.asyncio
async def test_require_plant_limit_basic_under_limit_passes() -> None:
    from app.plan_access import require_plant_limit

    tenant = _make_tenant(
        subscription_status="active", subscription_ends_at=_future(), plan="basic"
    )
    tenant.id = 7  # type: ignore[attr-defined]
    user = _make_user(tenant=tenant)

    # First execute: plant counts per plot (none with a map yet)
    plant_counts_result = _FakeResult([])
    # Second execute: plots with num_plants — 100 plants, under 500 limit
    plots_result = _FakeResult([(1, 100)])

    db = _FakeDB(plant_counts_result, plots_result)
    returned = await require_plant_limit(user=user, db=db)  # type: ignore[arg-type]
    assert returned is user


@pytest.mark.asyncio
async def test_require_plant_limit_basic_at_limit_raises() -> None:
    from app.plan_access import require_plant_limit

    tenant = _make_tenant(
        subscription_status="active", subscription_ends_at=_future(), plan="basic"
    )
    tenant.id = 7  # type: ignore[attr-defined]
    user = _make_user(tenant=tenant)

    # One plot mapped with 500 Plant rows → exactly at limit
    plant_counts_result = _FakeResult([_FakeRow(plot_id=1, cnt=500)])
    plots_result = _FakeResult([(1, 0)])  # num_plants ignored (map exists)

    db = _FakeDB(plant_counts_result, plots_result)
    with pytest.raises(PlantLimitExceededException) as exc_info:
        await require_plant_limit(user=user, db=db)  # type: ignore[arg-type]
    assert exc_info.value.limit == 500


@pytest.mark.asyncio
async def test_require_plant_limit_basic_mixed_mapped_and_manual() -> None:
    """Plot with map uses Plant rows; plot without map uses num_plants."""
    from app.plan_access import require_plant_limit

    tenant = _make_tenant(
        subscription_status="active", subscription_ends_at=_future(), plan="basic"
    )
    tenant.id = 7  # type: ignore[attr-defined]
    user = _make_user(tenant=tenant)

    # Plot 1 is mapped with 300 plants; plot 2 has no map and 150 num_plants → total 450
    plant_counts_result = _FakeResult([_FakeRow(plot_id=1, cnt=300)])
    plots_result = _FakeResult([(1, 0), (2, 150)])

    db = _FakeDB(plant_counts_result, plots_result)
    returned = await require_plant_limit(user=user, db=db)  # type: ignore[arg-type]
    assert returned is user

"""Plan access control: plan modes, feature gating, and write access guards."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.models.user import User

# Plan hierarchy (lowest to highest)
PLAN_HIERARCHY = ["basic", "premium", "enterprise"]

# Features available per plan. Trial has all features; read_only maps to basic.
# Only list RESTRICTED features here. Any feature NOT listed is treated as
# available on all plans (basic, premium, enterprise) — same as gastos/ingresos/parcelas.
_FEATURE_PLANS: dict[str, set[str]] = {
    "tiempo": {"premium", "enterprise"},
    "analitica_parcelas": {"premium", "enterprise"},
    "simulador_riego": {"premium", "enterprise"},
    "asistente_ia": {"premium", "enterprise"},
    "onboarding_ia": {"premium", "enterprise"},
    "tenants": {"enterprise"},
}

# Plant limits per plan (None = unlimited). Only Basic is capped; Premium and Enterprise are not.
PLANT_LIMIT_BASIC: int = 500

# Monthly onboarding session limits per plan. None = unlimited.
ONBOARDING_MONTHLY_LIMITS: dict[str, Optional[int]] = {
    "trial": 3,
    "basic": 0,  # blocked by feature gate, kept for completeness
    "premium": 5,
    "enterprise": None,
}


class WriteAccessDeniedException(Exception):
    """Raised when a read_only user attempts a write operation."""


class PlanUpgradeRequiredException(Exception):
    """Raised when a feature requires a higher-tier plan."""

    def __init__(self, feature: str, required_plan: str) -> None:
        self.feature = feature
        self.required_plan = required_plan
        super().__init__(f"Feature '{feature}' requires plan '{required_plan}'")


class PlantLimitExceededException(Exception):
    """Raised when adding plants would exceed the plan's plant limit."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(
            f"Has alcanzado el límite de {limit} plantas del plan Básico. "
            "Actualiza a Premium para plantas ilimitadas."
        )


class OnboardingQuotaExceededException(Exception):
    """Raised when the tenant exceeds the monthly onboarding session quota."""

    def __init__(self, limit: int, plan: str) -> None:
        self.limit = limit
        self.plan = plan
        super().__init__(
            f"Has alcanzado el límite de {limit} sesiones de onboarding "
            f"este mes para el plan {plan}."
        )


def get_plan_mode(user: User) -> str:
    """Return the effective plan mode for the user.

    Possible values:
    - "trial"       — active trial period
    - "read_only"   — trial expired, past_due, canceled, or expired active subscription
    - "basic"       — active subscription with plan='basic'
    - "premium"     — active subscription with plan='premium'
    - "enterprise"  — active subscription with plan='enterprise'

    Admin users always get "enterprise".
    """
    if user.role == "admin":
        return "enterprise"

    tenant = getattr(user, "active_tenant", None)
    if tenant is None:
        return "trial"

    now = datetime.now(UTC)
    sub_status: str = tenant.subscription_status

    if sub_status == "trialing":
        if tenant.trial_ends_at and tenant.trial_ends_at > now:
            return "trial"
        return "read_only"

    if sub_status == "active":
        if tenant.subscription_ends_at and tenant.subscription_ends_at <= now:
            return "read_only"
        plan: Optional[str] = getattr(tenant, "plan", None)
        if plan in ("basic", "premium", "enterprise"):
            return plan
        # Active subscription with no plan set → treat as basic (legacy / new signups)
        return "basic"

    # past_due, canceled, or any unknown status → read-only access
    return "read_only"


def is_read_only(user: User) -> bool:
    """Return True if the user is in read-only mode."""
    return get_plan_mode(user) == "read_only"


def has_feature(user: User, feature: str) -> bool:
    """Return True if the user's plan includes *feature*.

    Trial users have access to every feature.
    read_only users share the same feature set as 'basic'.
    """
    mode = get_plan_mode(user)

    if mode == "trial":
        return True

    # read_only maps to basic for feature resolution
    effective_plan = "basic" if mode == "read_only" else mode
    allowed = _FEATURE_PLANS.get(feature, {"basic", "premium", "enterprise"})
    return effective_plan in allowed


# ── FastAPI dependency: write access ─────────────────────────────────────────


async def require_write_access(
    user: User = Depends(require_subscription),
) -> User:
    """Block write operations when the user is in read-only mode."""
    if is_read_only(user):
        raise WriteAccessDeniedException()
    return user


# ── FastAPI dependency factory: feature gating ───────────────────────────────


def require_feature(feature: str):
    """Return a FastAPI dependency that blocks access when *feature* is not included
    in the user's plan.
    """

    async def _dep(user: User = Depends(require_subscription)) -> User:
        if not has_feature(user, feature):
            allowed = _FEATURE_PLANS.get(feature, {"basic"})
            required = next((p for p in PLAN_HIERARCHY if p in allowed), "premium")
            raise PlanUpgradeRequiredException(feature, required)
        return user

    return _dep


# ── FastAPI dependency: plant limit ──────────────────────────────────────────


async def require_plant_limit(
    user: User = Depends(require_write_access),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Enforce the Basic plan plant count limit before creating a new plant.

    The effective plant count per plot is:
    - Number of Plant rows if the plot has a configured map (Plant rows exist).
    - plot.num_plants otherwise (manual estimate, no map yet).

    Only the Basic plan is capped (500 total). Premium, Enterprise and Trial
    have no limit.
    """
    if get_plan_mode(user) != "basic":
        return user  # only basic is limited

    from sqlalchemy import func, select

    from app.models.plant import Plant
    from app.models.plot import Plot

    tenant_id: int = user.active_tenant.id  # type: ignore[union-attr]

    # Count Plant rows per plot for this tenant (plots that have a map configured)
    plant_counts_res = await db.execute(
        select(Plant.plot_id, func.count(Plant.id).label("cnt"))
        .where(Plant.tenant_id == tenant_id)
        .group_by(Plant.plot_id)
    )
    plant_counts: dict[int, int] = {row.plot_id: row.cnt for row in plant_counts_res.all()}

    # Fetch all plots with their num_plants estimate
    plots_res = await db.execute(
        select(Plot.id, Plot.num_plants).where(Plot.tenant_id == tenant_id)
    )
    # For each plot: use real plant count if map exists, else the manual estimate
    total: int = sum(
        plant_counts[plot_id] if plot_id in plant_counts else (num_plants or 0)
        for plot_id, num_plants in plots_res.all()
    )

    if total >= PLANT_LIMIT_BASIC:
        raise PlantLimitExceededException(PLANT_LIMIT_BASIC)

    return user

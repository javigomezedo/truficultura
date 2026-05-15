"""CRUD service for onboarding sessions.

Lives outside ``app/services/onboarding/`` (which is reserved for the agent
graph internals) so it can import models/database freely without circular
issues.

Every query filters by ``tenant_id`` to enforce multi-tenancy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.onboarding import OnboardingSession


async def create_session(
    db: AsyncSession,
    *,
    tenant_id: int,
    created_by_user_id: int | None,
    original_filename: str,
    initial_state: dict[str, Any] | None = None,
    status: str = "uploaded",
    entity_type: str | None = None,
    raw_file: bytes | None = None,
) -> OnboardingSession:
    session = OnboardingSession(
        tenant_id=tenant_id,
        created_by_user_id=created_by_user_id,
        status=status,
        entity_type=entity_type,
        original_filename=original_filename,
        state_json=initial_state or {},
        raw_file=raw_file,
    )
    db.add(session)
    await db.flush()
    return session


async def get_session(
    db: AsyncSession, session_id: int, tenant_id: int
) -> OnboardingSession | None:
    """Fetch a session by id, scoped to the given tenant."""
    result = await db.execute(
        select(OnboardingSession).where(
            OnboardingSession.id == session_id,
            OnboardingSession.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def list_sessions(
    db: AsyncSession, tenant_id: int, *, limit: int = 50
) -> list[OnboardingSession]:
    result = await db.execute(
        select(OnboardingSession)
        .where(OnboardingSession.tenant_id == tenant_id)
        .order_by(OnboardingSession.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def update_session_state(
    db: AsyncSession,
    session: OnboardingSession,
    *,
    state: dict[str, Any] | None = None,
    status: str | None = None,
    entity_type: str | None = None,
    error_message: str | None = None,
) -> OnboardingSession:
    if state is not None:
        # Replace wholesale; JSON column expects a new dict assignment so
        # SQLAlchemy detects the change.
        session.state_json = dict(state)
    if status is not None:
        session.status = status
    if entity_type is not None:
        session.entity_type = entity_type
    if error_message is not None:
        session.error_message = error_message
    await db.flush()
    return session


async def mark_cancelled(
    db: AsyncSession, session: OnboardingSession
) -> OnboardingSession:
    session.status = "cancelled"
    await db.flush()
    return session


async def count_sessions_this_month(
    db: AsyncSession, *, tenant_id: int, now: datetime | None = None
) -> int:
    """Count onboarding sessions created in the current calendar month.

    Used to enforce the per-plan monthly quota. Cancelled sessions count
    too: each upload consumes LLM tokens regardless of the outcome.
    """
    ref = now or datetime.now(UTC)
    month_start = datetime(ref.year, ref.month, 1, tzinfo=UTC)
    result = await db.execute(
        select(func.count(OnboardingSession.id)).where(
            OnboardingSession.tenant_id == tenant_id,
            OnboardingSession.created_at >= month_start,
        )
    )
    return int(result.scalar_one() or 0)


async def list_all_sessions_admin(
    db: AsyncSession,
    *,
    status: str | None = None,
    tenant_id: int | None = None,
    limit: int = 200,
) -> list[tuple[OnboardingSession, str | None, str | None]]:
    """Admin-only: list onboarding sessions across all tenants.

    Returns tuples ``(session, tenant_name, tenant_plan)`` ordered by most
    recent first. Filters by status/tenant when provided.
    """
    from app.models.tenant import Tenant

    stmt = (
        select(OnboardingSession, Tenant.name, Tenant.plan)
        .join(Tenant, Tenant.id == OnboardingSession.tenant_id, isouter=True)
        .order_by(OnboardingSession.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(OnboardingSession.status == status)
    if tenant_id is not None:
        stmt = stmt.where(OnboardingSession.tenant_id == tenant_id)
    result = await db.execute(stmt)
    return [(row[0], row[1], row[2]) for row in result.all()]

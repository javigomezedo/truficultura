from __future__ import annotations

import datetime
from datetime import timezone
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import User  # noqa: F401 - ensure metadata is loaded
from app.models.onboarding import OnboardingSession  # noqa: F401
from app.models.tenant import Tenant  # noqa: F401
from app.services import onboarding_service


async def _build_sessionmaker(db_file: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_maker


@pytest.mark.asyncio
async def test_count_sessions_this_month_filters_by_tenant_and_month(
    tmp_path: Path,
) -> None:
    """Real SQLite integration: validate the SQL of count_sessions_this_month."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "onboarding.sqlite3")

    now = datetime.datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc)
    month_start = datetime.datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)
    prev_month = datetime.datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)

    try:
        async with session_maker() as db:
            # Tenant A: 2 sessions this month + 1 last month
            db.add(
                OnboardingSession(
                    tenant_id=1,
                    status="imported",
                    original_filename="a1.xlsx",
                    state_json={},
                    created_at=month_start + datetime.timedelta(days=1),
                    updated_at=month_start + datetime.timedelta(days=1),
                )
            )
            db.add(
                OnboardingSession(
                    tenant_id=1,
                    status="cancelled",
                    original_filename="a2.xlsx",
                    state_json={},
                    created_at=month_start + datetime.timedelta(days=10),
                    updated_at=month_start + datetime.timedelta(days=10),
                )
            )
            db.add(
                OnboardingSession(
                    tenant_id=1,
                    status="imported",
                    original_filename="a_old.xlsx",
                    state_json={},
                    created_at=prev_month,
                    updated_at=prev_month,
                )
            )
            # Tenant B: 1 session this month (must not leak into tenant 1)
            db.add(
                OnboardingSession(
                    tenant_id=2,
                    status="uploaded",
                    original_filename="b1.xlsx",
                    state_json={},
                    created_at=month_start + datetime.timedelta(days=2),
                    updated_at=month_start + datetime.timedelta(days=2),
                )
            )
            await db.commit()

            # Tenant 1: 2 sessions this month (cancelled counts as well).
            count_a = await onboarding_service.count_sessions_this_month(
                db, tenant_id=1, now=now
            )
            assert count_a == 2

            # Tenant 2: only 1 session this month.
            count_b = await onboarding_service.count_sessions_this_month(
                db, tenant_id=2, now=now
            )
            assert count_b == 1

            # Tenant with no rows.
            count_empty = await onboarding_service.count_sessions_this_month(
                db, tenant_id=999, now=now
            )
            assert count_empty == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_all_sessions_admin_joins_tenant(tmp_path: Path) -> None:
    """Admin listing must join tenant name + plan via outer join."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "admin.sqlite3")

    try:
        async with session_maker() as db:
            db.add(
                Tenant(
                    id=1,
                    name="Acme Truffles",
                    slug="acme",
                    plan="premium",
                )
            )
            db.add(
                OnboardingSession(
                    tenant_id=1,
                    status="imported",
                    original_filename="ok.xlsx",
                    state_json={},
                )
            )
            db.add(
                OnboardingSession(
                    tenant_id=1,
                    status="error",
                    original_filename="bad.xlsx",
                    state_json={},
                )
            )
            # Orphan session whose tenant doesn't exist — outer join must still
            # return the row with NULL name/plan.
            db.add(
                OnboardingSession(
                    tenant_id=99,
                    status="uploaded",
                    original_filename="orphan.xlsx",
                    state_json={},
                )
            )
            await db.commit()

            rows = await onboarding_service.list_all_sessions_admin(db)
            assert len(rows) == 3

            # Filter by status.
            errors = await onboarding_service.list_all_sessions_admin(
                db, status="error"
            )
            assert len(errors) == 1
            session_row, name, plan = errors[0]
            assert session_row.original_filename == "bad.xlsx"
            assert name == "Acme Truffles"
            assert plan == "premium"

            # Filter by tenant.
            only_acme = await onboarding_service.list_all_sessions_admin(
                db, tenant_id=1
            )
            assert len(only_acme) == 2
            assert all(r[1] == "Acme Truffles" for r in only_acme)

            # Orphan still surfaces with NULL tenant fields.
            orphan = await onboarding_service.list_all_sessions_admin(db, tenant_id=99)
            assert len(orphan) == 1
            _, orphan_name, orphan_plan = orphan[0]
            assert orphan_name is None
            assert orphan_plan is None
    finally:
        await engine.dispose()

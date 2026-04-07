from __future__ import annotations

import datetime
from datetime import timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.truffle_event import TruffleEvent


async def create_event(
    db: AsyncSession,
    *,
    plant_id: int,
    plot_id: int,
    user_id: int,
    source: str = "manual",
) -> TruffleEvent:
    """Append a new truffle event for a plant. The undo window is fixed at 30 seconds."""
    now = datetime.datetime.now(tz=timezone.utc)
    event = TruffleEvent(
        plant_id=plant_id,
        plot_id=plot_id,
        user_id=user_id,
        source=source,
        created_at=now,
        undo_window_expires_at=now + timedelta(seconds=30),
    )
    db.add(event)
    await db.flush()
    return event


async def get_last_undoable_event(
    db: AsyncSession,
    *,
    plant_id: int,
    user_id: int,
) -> Optional[TruffleEvent]:
    """Return the most recent active event still within its undo window, or None."""
    now = datetime.datetime.now(tz=timezone.utc)
    res = await db.execute(
        select(TruffleEvent)
        .where(
            TruffleEvent.plant_id == plant_id,
            TruffleEvent.user_id == user_id,
            TruffleEvent.undone_at.is_(None),
            TruffleEvent.undo_window_expires_at > now,
        )
        .order_by(TruffleEvent.created_at.desc())
        .limit(1)
    )
    return res.scalar_one_or_none()


async def undo_last_event(
    db: AsyncSession,
    *,
    plant_id: int,
    user_id: int,
) -> Optional[TruffleEvent]:
    """Mark the last undoable event as undone. Returns the event or None if unavailable."""
    event = await get_last_undoable_event(db, plant_id=plant_id, user_id=user_id)
    if event is None:
        return None
    event.undone_at = datetime.datetime.now(tz=timezone.utc)
    await db.flush()
    return event


async def get_counts_by_plant(
    db: AsyncSession,
    *,
    plot_id: int,
    user_id: int,
    campaign_year: Optional[int] = None,
) -> dict[int, int]:
    """Return {plant_id: count} of active truffle events, optionally filtered by campaign."""
    filters = [
        TruffleEvent.plot_id == plot_id,
        TruffleEvent.user_id == user_id,
        TruffleEvent.undone_at.is_(None),
    ]
    if campaign_year is not None:
        start = datetime.datetime(campaign_year, 4, 1, tzinfo=timezone.utc)
        end = datetime.datetime(campaign_year + 1, 4, 1, tzinfo=timezone.utc)
        filters.extend(
            [TruffleEvent.created_at >= start, TruffleEvent.created_at < end]
        )

    q = (
        select(TruffleEvent.plant_id, func.count(TruffleEvent.id).label("cnt"))
        .where(*filters)
        .group_by(TruffleEvent.plant_id)
    )
    res = await db.execute(q)
    return {row.plant_id: row.cnt for row in res.all()}


async def list_events(
    db: AsyncSession,
    *,
    user_id: int,
    campaign_year: Optional[int] = None,
    plot_id: Optional[int] = None,
    plant_id: Optional[int] = None,
    limit: int = 200,
) -> list[TruffleEvent]:
    """Return active truffle events (most recent first) with optional filters."""
    filters = [
        TruffleEvent.user_id == user_id,
        TruffleEvent.undone_at.is_(None),
    ]
    if campaign_year is not None:
        start = datetime.datetime(campaign_year, 4, 1, tzinfo=timezone.utc)
        end = datetime.datetime(campaign_year + 1, 4, 1, tzinfo=timezone.utc)
        filters.extend(
            [TruffleEvent.created_at >= start, TruffleEvent.created_at < end]
        )
    if plot_id is not None:
        filters.append(TruffleEvent.plot_id == plot_id)
    if plant_id is not None:
        filters.append(TruffleEvent.plant_id == plant_id)

    res = await db.execute(
        select(TruffleEvent)
        .where(*filters)
        .order_by(TruffleEvent.created_at.desc())
        .limit(limit)
    )
    return res.scalars().all()

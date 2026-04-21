from __future__ import annotations

import datetime
from datetime import timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.truffle_event import TruffleEvent


def build_plot_event_summary(
    filtered_events: list[TruffleEvent],
    historical_active_events: list[TruffleEvent],
    *,
    campaign_harvest_totals: dict[int, float] | None = None,
    historical_harvest_totals: dict[int, float] | None = None,
) -> list[dict]:
    """Build per-plot summary rows for truffle reporting views.

    ``filtered_events`` are the events currently displayed by filters (usually campaign-filtered).
    ``historical_active_events`` should include active events without campaign restriction.
    ``campaign_harvest_totals`` and ``historical_harvest_totals`` are optional dicts
    {plot_id: grams} from PlotHarvest records that are added to the totals.
    """
    campaign_active = [
        e for e in filtered_events if getattr(e, "undone_at", None) is None
    ]

    campaign_by_plot: dict[int, float] = {}
    historical_by_plot: dict[int, float] = {}
    top_plants_by_plot: dict[int, dict[str, float]] = {}
    plot_names: dict[int, str] = {}

    for e in campaign_active:
        weight = float(getattr(e, "estimated_weight_grams", 1.0) or 0.0)
        campaign_by_plot[e.plot_id] = campaign_by_plot.get(e.plot_id, 0.0) + weight
        plot_obj = getattr(e, "plot", None)
        if plot_obj is not None and getattr(plot_obj, "name", None):
            plot_names[e.plot_id] = plot_obj.name

    for e in historical_active_events:
        weight = float(getattr(e, "estimated_weight_grams", 1.0) or 0.0)
        historical_by_plot[e.plot_id] = historical_by_plot.get(e.plot_id, 0.0) + weight
        plot_obj = getattr(e, "plot", None)
        if plot_obj is not None and getattr(plot_obj, "name", None):
            plot_names[e.plot_id] = plot_obj.name

        plant_label = str(e.plant_id)
        plant_obj = getattr(e, "plant", None)
        if plant_obj is not None and getattr(plant_obj, "label", None):
            plant_label = plant_obj.label
        top_plants_by_plot.setdefault(e.plot_id, {})
        top_plants_by_plot[e.plot_id][plant_label] = (
            top_plants_by_plot[e.plot_id].get(plant_label, 0.0) + weight
        )

    # Add PlotHarvest totals if provided
    _camp_harvests = campaign_harvest_totals or {}
    _hist_harvests = historical_harvest_totals or {}

    # Collect plot names from harvest data when not already known from events
    # (no plot object available here, names resolved in router layer if needed)

    all_plot_ids = (
        set(campaign_by_plot)
        | set(historical_by_plot)
        | set(_camp_harvests)
        | set(_hist_harvests)
    )

    rows: list[dict] = []
    for pid in sorted(all_plot_ids):
        plant_counts = top_plants_by_plot.get(pid, {})
        top_plants = sorted(
            plant_counts.items(), key=lambda item: item[1], reverse=True
        )[:3]
        campaign_total = round(
            campaign_by_plot.get(pid, 0.0) + _camp_harvests.get(pid, 0.0), 2
        )
        historical_total = round(
            historical_by_plot.get(pid, 0.0) + _hist_harvests.get(pid, 0.0), 2
        )
        rows.append(
            {
                "plot_id": pid,
                "plot_name": plot_names.get(pid, f"Parcela {pid}"),
                "campaign_total": campaign_total,
                "historical_total": historical_total,
                "top_plants": top_plants,
            }
        )
    return rows


async def create_event(
    db: AsyncSession,
    *,
    plant_id: int,
    plot_id: int,
    user_id: int,
    estimated_weight_grams: float = 1.0,
    source: str = "manual",
    dedupe_window_seconds: int = 2,
) -> TruffleEvent:
    """Append a truffle event for a plant.

    To avoid rapid double taps/scans, if there is already an active event for the same
    user/plot/plant within ``dedupe_window_seconds`` it is returned and no new row is created.
    The undo window for created events is fixed at 30 seconds.
    """
    now = datetime.datetime.now(tz=timezone.utc)
    dedupe_since = now - timedelta(seconds=max(dedupe_window_seconds, 0))

    duplicate_res = await db.execute(
        select(TruffleEvent)
        .where(
            TruffleEvent.plant_id == plant_id,
            TruffleEvent.plot_id == plot_id,
            TruffleEvent.user_id == user_id,
            TruffleEvent.undone_at.is_(None),
            TruffleEvent.created_at >= dedupe_since,
        )
        .order_by(TruffleEvent.created_at.desc())
        .limit(1)
    )
    duplicate = duplicate_res.scalar_one_or_none()
    if duplicate is not None:
        return duplicate

    event = TruffleEvent(
        plant_id=plant_id,
        plot_id=plot_id,
        user_id=user_id,
        source=source,
        estimated_weight_grams=max(float(estimated_weight_grams), 0.0),
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
    """Hard-delete the last undoable event. Returns the deleted event or None."""
    event = await get_last_undoable_event(db, plant_id=plant_id, user_id=user_id)
    if event is None:
        return None
    await db.delete(event)
    await db.flush()
    return event


async def delete_event(
    db: AsyncSession,
    *,
    event_id: int,
    user_id: int,
) -> bool:
    """Delete a truffle event by id for the given user. Returns True if deleted."""
    res = await db.execute(
        select(TruffleEvent).where(
            TruffleEvent.id == event_id,
            TruffleEvent.user_id == user_id,
        )
    )
    event = res.scalar_one_or_none()
    if event is None:
        return False

    await db.delete(event)
    await db.flush()
    return True


async def get_counts_by_plant(
    db: AsyncSession,
    *,
    plot_id: int,
    user_id: int,
    campaign_year: Optional[int] = None,
) -> dict[int, float]:
    """Return {plant_id: grams} of active truffle events, optionally filtered by campaign."""
    filters = [
        TruffleEvent.plot_id == plot_id,
        TruffleEvent.user_id == user_id,
        TruffleEvent.undone_at.is_(None),
    ]
    if campaign_year is not None:
        start = datetime.datetime(campaign_year, 5, 1, tzinfo=timezone.utc)
        end = datetime.datetime(campaign_year + 1, 5, 1, tzinfo=timezone.utc)
        filters.extend(
            [TruffleEvent.created_at >= start, TruffleEvent.created_at < end]
        )

    q = (
        select(
            TruffleEvent.plant_id,
            func.sum(func.coalesce(TruffleEvent.estimated_weight_grams, 1.0)).label(
                "total_grams"
            ),
        )
        .where(*filters)
        .group_by(TruffleEvent.plant_id)
    )
    res = await db.execute(q)
    return {row.plant_id: round(float(row.total_grams or 0.0), 2) for row in res.all()}


async def list_events(
    db: AsyncSession,
    *,
    user_id: int,
    campaign_year: Optional[int] = None,
    plot_id: Optional[int] = None,
    plant_id: Optional[int] = None,
    include_undone: bool = True,
    limit: int = 200,
) -> list[TruffleEvent]:
    """Return truffle events (most recent first) with optional filters."""
    filters = [TruffleEvent.user_id == user_id]
    if not include_undone:
        filters.append(TruffleEvent.undone_at.is_(None))
    if campaign_year is not None:
        start = datetime.datetime(campaign_year, 5, 1, tzinfo=timezone.utc)
        end = datetime.datetime(campaign_year + 1, 5, 1, tzinfo=timezone.utc)
        filters.extend(
            [TruffleEvent.created_at >= start, TruffleEvent.created_at < end]
        )
    if plot_id is not None:
        filters.append(TruffleEvent.plot_id == plot_id)
    if plant_id is not None:
        filters.append(TruffleEvent.plant_id == plant_id)

    res = await db.execute(
        select(TruffleEvent)
        .options(
            selectinload(TruffleEvent.plant),
            selectinload(TruffleEvent.plot),
            selectinload(TruffleEvent.user),
        )
        .where(*filters)
        .order_by(TruffleEvent.created_at.desc())
        .limit(limit)
    )
    return res.scalars().all()

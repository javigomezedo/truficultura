from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.plot_harvest import PlotHarvest
from app.utils import campaign_year


async def create_harvest(
    db: AsyncSession,
    *,
    user_id: int,
    plot_id: int,
    harvest_date: datetime.date,
    weight_grams: float,
    notes: Optional[str] = None,
) -> PlotHarvest:
    harvest = PlotHarvest(
        user_id=user_id,
        plot_id=plot_id,
        harvest_date=harvest_date,
        weight_grams=max(0.0, float(weight_grams)),
        notes=notes or None,
    )
    db.add(harvest)
    await db.flush()
    return harvest


async def create_harvests_batch(
    db: AsyncSession,
    *,
    user_id: int,
    entries: list[dict],
) -> list[PlotHarvest]:
    """Create multiple harvests in a single call.

    Each entry must contain: plot_id, harvest_date, weight_grams.
    Optionally: notes.
    Entries with weight_grams <= 0 are skipped.
    """
    harvests: list[PlotHarvest] = []
    for entry in entries:
        weight = float(entry.get("weight_grams", 0.0) or 0.0)
        if weight <= 0:
            continue
        harvest = PlotHarvest(
            user_id=user_id,
            plot_id=int(entry["plot_id"]),
            harvest_date=entry["harvest_date"],
            weight_grams=weight,
            notes=entry.get("notes") or None,
        )
        db.add(harvest)
        harvests.append(harvest)
    if harvests:
        await db.flush()
    return harvests


async def list_harvests(
    db: AsyncSession,
    *,
    user_id: int,
    campaign_year_filter: Optional[int] = None,
    plot_id: Optional[int] = None,
    limit: int = 500,
) -> list[PlotHarvest]:
    filters = [PlotHarvest.user_id == user_id]
    if plot_id is not None:
        filters.append(PlotHarvest.plot_id == plot_id)
    if campaign_year_filter is not None:
        start = datetime.date(campaign_year_filter, 5, 1)
        end = datetime.date(campaign_year_filter + 1, 5, 1)
        filters.extend(
            [PlotHarvest.harvest_date >= start, PlotHarvest.harvest_date < end]
        )
    res = await db.execute(
        select(PlotHarvest)
        .options(selectinload(PlotHarvest.plot))
        .where(*filters)
        .order_by(PlotHarvest.harvest_date.desc())
        .limit(limit)
    )
    return res.scalars().all()


async def get_harvest(
    db: AsyncSession,
    *,
    harvest_id: int,
    user_id: int,
) -> Optional[PlotHarvest]:
    res = await db.execute(
        select(PlotHarvest)
        .options(selectinload(PlotHarvest.plot))
        .where(PlotHarvest.id == harvest_id, PlotHarvest.user_id == user_id)
    )
    return res.scalar_one_or_none()


async def update_harvest(
    db: AsyncSession,
    *,
    harvest_id: int,
    user_id: int,
    harvest_date: Optional[datetime.date] = None,
    weight_grams: Optional[float] = None,
    notes: Optional[str] = None,
) -> Optional[PlotHarvest]:
    harvest = await get_harvest(db, harvest_id=harvest_id, user_id=user_id)
    if harvest is None:
        return None
    if harvest_date is not None:
        harvest.harvest_date = harvest_date
    if weight_grams is not None:
        harvest.weight_grams = max(0.0, float(weight_grams))
    if notes is not None:
        harvest.notes = notes or None
    await db.flush()
    return harvest


async def delete_harvest(
    db: AsyncSession,
    *,
    harvest_id: int,
    user_id: int,
) -> bool:
    harvest = await get_harvest(db, harvest_id=harvest_id, user_id=user_id)
    if harvest is None:
        return False
    await db.delete(harvest)
    await db.flush()
    return True


async def get_totals_by_plot(
    db: AsyncSession,
    *,
    user_id: int,
    campaign_year_filter: Optional[int] = None,
) -> dict[int, float]:
    """Return {plot_id: total_weight_grams} for all plot harvests of the user.

    Optionally filtered to a single campaign year (May–April).
    """
    filters = [PlotHarvest.user_id == user_id]
    if campaign_year_filter is not None:
        start = datetime.date(campaign_year_filter, 5, 1)
        end = datetime.date(campaign_year_filter + 1, 5, 1)
        filters.extend(
            [PlotHarvest.harvest_date >= start, PlotHarvest.harvest_date < end]
        )
    res = await db.execute(
        select(PlotHarvest.plot_id, PlotHarvest.weight_grams).where(*filters)
    )
    totals: dict[int, float] = {}
    for row in res.all():
        totals[row.plot_id] = round(
            totals.get(row.plot_id, 0.0) + float(row.weight_grams or 0.0), 2
        )
    return totals


async def get_campaign_years(
    db: AsyncSession,
    *,
    user_id: int,
) -> list[int]:
    """Return sorted list of distinct campaign years with harvest data (most recent first)."""
    res = await db.execute(
        select(PlotHarvest.harvest_date).where(PlotHarvest.user_id == user_id)
    )
    years = sorted(
        {campaign_year(row.harvest_date) for row in res.all()},
        reverse=True,
    )
    return years

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plant_presence import PlantPresence
from app.utils import campaign_year


async def toggle_presence(
    db: AsyncSession,
    *,
    user_id: int,
    plant_id: int,
    plot_id: int,
    presence_date: datetime.date,
) -> Optional[PlantPresence]:
    """Toggle presence for a plant on a date.

    If no record exists, creates one with has_truffle=True.
    If a record already exists, deletes it and returns None.
    """
    res = await db.execute(
        select(PlantPresence).where(
            PlantPresence.plant_id == plant_id,
            PlantPresence.user_id == user_id,
            PlantPresence.presence_date == presence_date,
        )
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        await db.delete(existing)
        await db.flush()
        return None

    presence = PlantPresence(
        user_id=user_id,
        plot_id=plot_id,
        plant_id=plant_id,
        presence_date=presence_date,
        has_truffle=True,
    )
    db.add(presence)
    await db.flush()
    return presence


async def get_presences_by_plot(
    db: AsyncSession,
    *,
    user_id: int,
    plot_id: int,
    campaign_year_filter: Optional[int] = None,
) -> dict[int, bool]:
    """Return {plant_id: True} for all plants with presence marks.

    Optionally filtered to a single campaign year (May–April).
    If campaign_year_filter is None, returns all historical presences.
    """
    filters = [
        PlantPresence.user_id == user_id,
        PlantPresence.plot_id == plot_id,
        PlantPresence.has_truffle.is_(True),
    ]
    if campaign_year_filter is not None:
        start = datetime.date(campaign_year_filter, 5, 1)
        end = datetime.date(campaign_year_filter + 1, 5, 1)
        filters.extend(
            [
                PlantPresence.presence_date >= start,
                PlantPresence.presence_date < end,
            ]
        )
    res = await db.execute(select(PlantPresence.plant_id).where(*filters))
    return {row.plant_id: True for row in res.all()}


async def get_presence_dates_for_plant(
    db: AsyncSession,
    *,
    user_id: int,
    plant_id: int,
) -> list[datetime.date]:
    """Return all presence dates for a single plant, sorted descending."""
    res = await db.execute(
        select(PlantPresence.presence_date)
        .where(
            PlantPresence.plant_id == plant_id,
            PlantPresence.user_id == user_id,
            PlantPresence.has_truffle.is_(True),
        )
        .order_by(PlantPresence.presence_date.desc())
    )
    return [row.presence_date for row in res.all()]


async def get_campaign_years(
    db: AsyncSession,
    *,
    user_id: int,
    plot_id: int,
) -> list[int]:
    """Return sorted list of distinct campaign years with presence data for a plot."""
    res = await db.execute(
        select(PlantPresence.presence_date).where(
            PlantPresence.user_id == user_id,
            PlantPresence.plot_id == plot_id,
        )
    )
    years = sorted(
        {campaign_year(row.presence_date) for row in res.all()},
        reverse=True,
    )
    return years

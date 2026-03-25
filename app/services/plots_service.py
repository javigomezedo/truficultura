from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plot import Plot


async def list_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def get_plot(db: AsyncSession, plot_id: int, user_id: int) -> Optional[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.id == plot_id, Plot.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _recalculate_percentages(db: AsyncSession, user_id: int) -> None:
    """Recalculate percentages for all plots of a user based on their surface area."""
    result = await db.execute(select(Plot).where(Plot.user_id == user_id))
    plots = result.scalars().all()

    # Calculate total area from plots that have area_ha defined
    total_area = sum(p.area_ha or 0 for p in plots)

    # If no area defined, leave all percentages at 0
    if total_area == 0:
        for plot in plots:
            plot.percentage = 0.0
    else:
        # Calculate percentage for each plot
        for plot in plots:
            if plot.area_ha is not None:
                plot.percentage = (plot.area_ha / total_area) * 100
            else:
                plot.percentage = 0.0

    await db.flush()


async def create_plot(
    db: AsyncSession,
    *,
    user_id: int,
    name: str,
    polygon: str,
    cadastral_ref: str,
    hydrant: str,
    sector: str,
    num_holm_oaks: int,
    planting_date: datetime.date,
    area_ha: Optional[float],
    production_start: Optional[datetime.date],
) -> Plot:
    new_plot = Plot(
        user_id=user_id,
        name=name,
        polygon=polygon,
        cadastral_ref=cadastral_ref,
        hydrant=hydrant,
        sector=sector,
        num_holm_oaks=num_holm_oaks,
        planting_date=planting_date,
        area_ha=area_ha,
        production_start=production_start,
        percentage=0.0,
    )
    db.add(new_plot)
    await db.flush()

    # Recalculate all percentages for this user
    await _recalculate_percentages(db, user_id)

    return new_plot


async def update_plot(
    db: AsyncSession,
    plot: Plot,
    *,
    name: str,
    polygon: str,
    cadastral_ref: str,
    hydrant: str,
    sector: str,
    num_holm_oaks: int,
    planting_date: datetime.date,
    area_ha: Optional[float],
    production_start: Optional[datetime.date],
) -> Plot:
    plot.name = name
    plot.polygon = polygon
    plot.cadastral_ref = cadastral_ref
    plot.hydrant = hydrant
    plot.sector = sector
    plot.num_holm_oaks = num_holm_oaks
    plot.planting_date = planting_date
    plot.area_ha = area_ha
    plot.production_start = production_start
    await db.flush()

    # Recalculate all percentages for this user
    await _recalculate_percentages(db, plot.user_id)

    return plot


async def delete_plot(db: AsyncSession, plot: Plot) -> None:
    user_id = plot.user_id
    await db.delete(plot)
    await db.flush()

    # Recalculate percentages for remaining plots
    if user_id:
        await _recalculate_percentages(db, user_id)

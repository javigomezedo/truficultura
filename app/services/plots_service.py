from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plant import Plant
from app.models.plot import Plot


async def list_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def get_plant_counts_by_plot(db: AsyncSession, user_id: int) -> dict[int, int]:
    """Return a mapping of plot_id → number of Plant rows currently in the DB."""
    res = await db.execute(
        select(Plant.plot_id, func.count(Plant.id).label("cnt"))
        .where(Plant.user_id == user_id)
        .group_by(Plant.plot_id)
    )
    return {row.plot_id: row.cnt for row in res.all()}


async def get_plot(db: AsyncSession, plot_id: int, user_id: int) -> Optional[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.id == plot_id, Plot.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _recalculate_percentages(db: AsyncSession, user_id: int) -> None:
    """Recalculate percentages for all plots of a user based on their plant count."""
    result = await db.execute(select(Plot).where(Plot.user_id == user_id))
    plots = result.scalars().all()

    # Calculate total plants from all plots
    total_plants = sum(p.num_plants or 0 for p in plots)

    # If no plants defined, leave all percentages at 0
    if total_plants == 0:
        for plot in plots:
            plot.percentage = 0.0
    else:
        # Calculate percentage for each plot
        for plot in plots:
            if plot.num_plants is not None and plot.num_plants > 0:
                plot.percentage = (plot.num_plants / total_plants) * 100
            else:
                plot.percentage = 0.0

    await db.flush()


async def create_plot(
    db: AsyncSession,
    *,
    user_id: int,
    name: str,
    polygon: str,
    plot_num: str,
    cadastral_ref: str,
    hydrant: str,
    sector: str,
    num_plants: int,
    planting_date: datetime.date,
    area_ha: Optional[float],
    production_start: Optional[datetime.date],
    has_irrigation: bool = False,
    provincia_cod: Optional[str] = None,
    municipio_cod: Optional[str] = None,
) -> Plot:
    new_plot = Plot(
        user_id=user_id,
        name=name,
        polygon=polygon,
        plot_num=plot_num,
        cadastral_ref=cadastral_ref,
        hydrant=hydrant,
        sector=sector,
        num_plants=num_plants,
        planting_date=planting_date,
        area_ha=area_ha,
        production_start=production_start,
        percentage=0.0,
        has_irrigation=has_irrigation,
        provincia_cod=provincia_cod or None,
        municipio_cod=municipio_cod or None,
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
    plot_num: str,
    cadastral_ref: str,
    hydrant: str,
    sector: str,
    num_plants: int,
    planting_date: datetime.date,
    area_ha: Optional[float],
    production_start: Optional[datetime.date],
    has_irrigation: bool = False,
    provincia_cod: Optional[str] = None,
    municipio_cod: Optional[str] = None,
) -> Plot:
    plot.name = name
    plot.polygon = polygon
    plot.plot_num = plot_num
    plot.cadastral_ref = cadastral_ref
    plot.hydrant = hydrant
    plot.sector = sector
    plot.num_plants = num_plants
    plot.planting_date = planting_date
    plot.area_ha = area_ha
    plot.production_start = production_start
    plot.has_irrigation = has_irrigation
    plot.provincia_cod = provincia_cod or None
    plot.municipio_cod = municipio_cod or None
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

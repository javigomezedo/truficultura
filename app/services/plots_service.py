from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plant import Plant, PlantStatus
from app.models.plot import Plot


async def list_plots(db: AsyncSession, tenant_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.tenant_id == tenant_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def get_plant_counts_by_plot(db: AsyncSession, tenant_id: int) -> dict[int, int]:
    """Return a mapping of plot_id → number of Plant rows currently in the DB."""
    res = await db.execute(
        select(Plant.plot_id, func.count(Plant.id).label("cnt"))
        .where(Plant.tenant_id == tenant_id)
        .group_by(Plant.plot_id)
    )
    return {row.plot_id: row.cnt for row in res.all()}


async def _get_effective_plant_total(
    db: AsyncSession,
    tenant_id: int,
    *,
    exclude_plot_id: Optional[int] = None,
) -> int:
    """Effective plant total across all tenant plots.

    Uses Plant row count for plots with a configured map; falls back to
    plot.num_plants for plots without a map. An optional plot can be
    excluded so callers can compute the delta for create/update scenarios.
    """
    plant_counts_res = await db.execute(
        select(Plant.plot_id, func.count(Plant.id).label("cnt"))
        .where(Plant.tenant_id == tenant_id, Plant.status != PlantStatus.muerta)
        .group_by(Plant.plot_id)
    )
    plant_counts: dict[int, int] = {row.plot_id: row.cnt for row in plant_counts_res.all()}

    plots_q = select(Plot.id, Plot.num_plants).where(Plot.tenant_id == tenant_id)
    if exclude_plot_id is not None:
        plots_q = plots_q.where(Plot.id != exclude_plot_id)
    plots_res = await db.execute(plots_q)

    return sum(
        plant_counts[plot_id] if plot_id in plant_counts else (num_plants or 0)
        for plot_id, num_plants in plots_res.all()
    )


async def get_plot(db: AsyncSession, plot_id: int, tenant_id: int) -> Optional[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.id == plot_id, Plot.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def _recalculate_percentages(db: AsyncSession, tenant_id: int) -> None:
    """Recalculate percentages for all plots of a tenant based on their plant count."""
    result = await db.execute(select(Plot).where(Plot.tenant_id == tenant_id))
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
    tenant_id: int,
    acting_user_id: Optional[int] = None,
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
    recinto: str = "1",
    caudal_riego: Optional[float] = None,
    provincia_cod: Optional[str] = None,
    municipio_cod: Optional[str] = None,
    plant_limit: Optional[int] = None,
) -> Plot:
    if plant_limit is not None and num_plants > 0:
        current = await _get_effective_plant_total(db, tenant_id)
        if current + num_plants > plant_limit:
            from app.plan_access import PlantLimitExceededException
            raise PlantLimitExceededException(plant_limit)

    new_plot = Plot(
        tenant_id=tenant_id,
        created_by_user_id=acting_user_id,
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
        recinto=recinto,
        caudal_riego=caudal_riego,
        provincia_cod=provincia_cod or None,
        municipio_cod=municipio_cod or None,
    )
    db.add(new_plot)
    await db.flush()

    # Recalculate all percentages for this tenant
    await _recalculate_percentages(db, tenant_id)

    return new_plot


async def update_plot(
    db: AsyncSession,
    plot: Plot,
    *,
    acting_user_id: Optional[int] = None,
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
    recinto: str = "1",
    caudal_riego: Optional[float] = None,
    provincia_cod: Optional[str] = None,
    municipio_cod: Optional[str] = None,
    plant_limit: Optional[int] = None,
) -> Plot:
    # Enforce the limit when num_plants increases.
    # We always check against _get_effective_plant_total which uses Plant rows for
    # mapped plots and num_plants for unmapped ones. This also prevents storing a
    # num_plants value larger than the limit on mapped plots (which would become the
    # effective count if the map were later deleted).
    if plant_limit is not None and num_plants > (plot.num_plants or 0):
        other_total = await _get_effective_plant_total(
            db, plot.tenant_id, exclude_plot_id=plot.id
        )
        if other_total + num_plants > plant_limit:
            from app.plan_access import PlantLimitExceededException
            raise PlantLimitExceededException(plant_limit)

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
    plot.recinto = recinto
    plot.caudal_riego = caudal_riego
    plot.provincia_cod = provincia_cod or None
    plot.municipio_cod = municipio_cod or None
    plot.updated_by_user_id = acting_user_id
    await db.flush()

    # Recalculate all percentages for this tenant
    await _recalculate_percentages(db, plot.tenant_id)

    return plot


async def delete_plot(db: AsyncSession, plot: Plot) -> None:
    tenant_id = plot.tenant_id
    await db.delete(plot)
    await db.flush()

    # Recalculate percentages for remaining plots
    if tenant_id:
        await _recalculate_percentages(db, tenant_id)

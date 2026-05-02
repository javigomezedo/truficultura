from __future__ import annotations

import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.expense import Expense
from app.models.plot import Plot
from app.models.well import Well
from app.schemas.well import WellCreate, WellUpdate
from app.utils import campaign_year


async def get_well(db: AsyncSession, well_id: int, tenant_id: int) -> Optional[Well]:
    result = await db.execute(
        select(Well).where(Well.id == well_id, Well.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def list_wells(
    db: AsyncSession,
    tenant_id: int,
    *,
    plot_id: Optional[int] = None,
    year: Optional[int] = None,
) -> list[Well]:
    stmt = select(Well).where(Well.tenant_id == tenant_id)
    if plot_id is not None:
        stmt = stmt.where(Well.plot_id == plot_id)
    wells_result = await db.execute(stmt.order_by(Well.date.desc()))
    wells = wells_result.scalars().all()
    if year is not None:
        wells = [w for w in wells if campaign_year(w.date) == year]
    return wells


async def _get_all_years(db: AsyncSession, tenant_id: int) -> list[int]:
    result = await db.execute(select(Well.date).where(Well.tenant_id == tenant_id))
    dates = result.scalars().all()
    years = sorted({campaign_year(d) for d in dates}, reverse=True)
    return years


async def _get_all_plots(db: AsyncSession, tenant_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.tenant_id == tenant_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def get_wells_list_context(
    db: AsyncSession,
    tenant_id: int,
    *,
    year: Optional[int] = None,
    plot_id: Optional[int] = None,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    wells = await list_wells(db, tenant_id, plot_id=plot_id, year=year)
    plots = await _get_all_plots(db, tenant_id)
    years = await _get_all_years(db, tenant_id)

    _SORT_KEYS: dict = {
        "date": lambda x: x.date,
        "plot": lambda x: x.plot.name if x.plot else "",
        "wells_per_plant": lambda x: x.wells_per_plant,
    }
    key_fn = _SORT_KEYS.get(sort_by, lambda x: x.date)
    wells = sorted(wells, key=key_fn, reverse=(sort_order == "desc"))

    total_wells_per_plant = sum(w.wells_per_plant for w in wells)
    total_estimated_wells = sum(
        w.wells_per_plant * (w.plot.num_plants if w.plot is not None else 0)
        for w in wells
    )

    return {
        "records": wells,
        "plots": plots,
        "years": years,
        "selected_year": year,
        "selected_plot": plot_id,
        "total_wells_per_plant": total_wells_per_plant,
        "total_estimated_wells": total_estimated_wells,
        "count": len(wells),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


async def get_well_expenses_for_plot(
    db: AsyncSession, tenant_id: int, plot_id: int
) -> list[Expense]:
    result = await db.execute(
        select(Expense)
        .where(
            Expense.tenant_id == tenant_id,
            Expense.plot_id == plot_id,
            Expense.category == "Pozos",
        )
        .order_by(Expense.date.desc())
    )
    return result.scalars().all()


async def create_well(db: AsyncSession, tenant_id: int, data: WellCreate, acting_user_id: Optional[int] = None) -> Well:
    from app.services.plot_events_service import sync_plot_event_from_well

    plot_result = await db.execute(
        select(Plot).where(Plot.id == data.plot_id, Plot.tenant_id == tenant_id)
    )
    plot = plot_result.scalar_one_or_none()
    if plot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Parcela no encontrada"),
        )

    if data.expense_id is not None:
        expense_result = await db.execute(
            select(Expense).where(
                Expense.id == data.expense_id,
                Expense.tenant_id == tenant_id,
                Expense.plot_id == data.plot_id,
                Expense.category == "Pozos",
            )
        )
        if expense_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_(
                    "El gasto debe pertenecer a la misma parcela y tener categoría 'Pozos'"
                ),
            )

    record = Well(
        tenant_id=tenant_id,
        created_by_user_id=acting_user_id,
        plot_id=data.plot_id,
        date=data.date,
        wells_per_plant=data.wells_per_plant,
        expense_id=data.expense_id,
        notes=data.notes,
    )
    db.add(record)
    await db.flush()
    await sync_plot_event_from_well(db, record)
    return record


async def update_well(db: AsyncSession, record: Well, data: WellUpdate, acting_user_id: Optional[int] = None) -> Well:
    from app.services.plot_events_service import sync_plot_event_from_well

    target_plot_id = data.plot_id if data.plot_id is not None else record.plot_id
    if data.plot_id is not None:
        plot_result = await db.execute(
            select(Plot).where(Plot.id == data.plot_id, Plot.tenant_id == record.tenant_id)
        )
        if plot_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("Parcela no encontrada"),
            )
        record.plot_id = data.plot_id
    if data.date is not None:
        record.date = data.date
    if data.wells_per_plant is not None:
        record.wells_per_plant = data.wells_per_plant
    if data.expense_id is not None:
        expense_result = await db.execute(
            select(Expense).where(
                Expense.id == data.expense_id,
                Expense.tenant_id == record.tenant_id,
                Expense.plot_id == target_plot_id,
                Expense.category == "Pozos",
            )
        )
        if expense_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_(
                    "El gasto debe pertenecer a la misma parcela y tener categoría 'Pozos'"
                ),
            )
        record.expense_id = data.expense_id
    else:
        if "expense_id" in data.model_fields_set:
            record.expense_id = None
    if data.notes is not None:
        record.notes = data.notes
    elif "notes" in data.model_fields_set:
        record.notes = None
    record.updated_by_user_id = acting_user_id
    await db.flush()
    await sync_plot_event_from_well(db, record)
    return record


async def delete_well(db: AsyncSession, well_id: int, tenant_id: int) -> None:
    from app.services.plot_events_service import delete_plot_event_for_well

    record = await get_well(db, well_id, tenant_id)
    if record is not None:
        await delete_plot_event_for_well(db, well_id, tenant_id)
        await db.delete(record)
        await db.flush()

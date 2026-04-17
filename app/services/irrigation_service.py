from __future__ import annotations

import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.expense import Expense
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.schemas.irrigation import IrrigationCreate, IrrigationUpdate
from app.utils import campaign_year


async def get_irrigation_record(
    db: AsyncSession, record_id: int, user_id: int
) -> Optional[IrrigationRecord]:
    result = await db.execute(
        select(IrrigationRecord).where(
            IrrigationRecord.id == record_id,
            IrrigationRecord.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_irrigation_records(
    db: AsyncSession,
    user_id: int,
    *,
    plot_id: Optional[int] = None,
    year: Optional[int] = None,
) -> list[IrrigationRecord]:
    stmt = select(IrrigationRecord).where(IrrigationRecord.user_id == user_id)
    if plot_id is not None:
        stmt = stmt.where(IrrigationRecord.plot_id == plot_id)
    records_result = await db.execute(stmt.order_by(IrrigationRecord.date.desc()))
    records = records_result.scalars().all()

    if year is not None:
        records = [r for r in records if campaign_year(r.date) == year]

    return records


async def _get_all_years(db: AsyncSession, user_id: int) -> list[int]:
    result = await db.execute(
        select(IrrigationRecord.date).where(IrrigationRecord.user_id == user_id)
    )
    dates = result.scalars().all()
    years = sorted({campaign_year(d) for d in dates}, reverse=True)
    return years


async def _get_irrigable_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot)
        .where(Plot.user_id == user_id, Plot.has_irrigation.is_(True))
        .order_by(Plot.name)
    )
    return result.scalars().all()


async def get_irrigation_list_context(
    db: AsyncSession,
    user_id: int,
    *,
    year: Optional[int] = None,
    plot_id: Optional[int] = None,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    records = await list_irrigation_records(db, user_id, plot_id=plot_id, year=year)
    plots = await _get_irrigable_plots(db, user_id)
    years = await _get_all_years(db, user_id)

    _SORT_KEYS: dict = {
        "date": lambda x: x.date,
        "plot": lambda x: x.plot.name if x.plot else "",
        "water_m3": lambda x: x.water_m3,
    }
    key_fn = _SORT_KEYS.get(sort_by, lambda x: x.date)
    records = sorted(records, key=key_fn, reverse=(sort_order == "desc"))

    total_water_m3 = sum(r.water_m3 for r in records)

    return {
        "records": records,
        "plots": plots,
        "years": years,
        "selected_year": year,
        "selected_plot": plot_id,
        "total_water_m3": round(total_water_m3, 3),
        "total_water_liters": round(total_water_m3 * 1000, 1),
        "count": len(records),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


async def get_riego_expenses_for_plot(
    db: AsyncSession, user_id: int, plot_id: int
) -> list[Expense]:
    result = await db.execute(
        select(Expense)
        .where(
            Expense.user_id == user_id,
            Expense.plot_id == plot_id,
            Expense.category == "Riego",
        )
        .order_by(Expense.date.desc())
    )
    return result.scalars().all()


async def create_irrigation_record(
    db: AsyncSession, user_id: int, data: IrrigationCreate
) -> IrrigationRecord:
    from app.services.plot_events_service import sync_plot_event_from_irrigation

    # Validate plot belongs to user and has irrigation enabled
    plot_result = await db.execute(
        select(Plot).where(Plot.id == data.plot_id, Plot.user_id == user_id)
    )
    plot = plot_result.scalar_one_or_none()
    if plot is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Parcela no encontrada"),
        )
    if not plot.has_irrigation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("La parcela no tiene sistema de riego activado"),
        )

    # Validate expense if provided
    if data.expense_id is not None:
        expense_result = await db.execute(
            select(Expense).where(
                Expense.id == data.expense_id,
                Expense.user_id == user_id,
                Expense.plot_id == data.plot_id,
                Expense.category == "Riego",
            )
        )
        if expense_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_(
                    "El gasto debe pertenecer a la misma parcela y tener categoría 'Riego'"
                ),
            )

    record = IrrigationRecord(
        user_id=user_id,
        plot_id=data.plot_id,
        date=data.date,
        water_m3=data.water_m3,
        expense_id=data.expense_id,
        notes=data.notes,
    )
    db.add(record)
    await db.flush()
    await sync_plot_event_from_irrigation(db, record)
    return record


async def update_irrigation_record(
    db: AsyncSession, record: IrrigationRecord, data: IrrigationUpdate
) -> IrrigationRecord:
    from app.services.plot_events_service import sync_plot_event_from_irrigation

    if data.date is not None:
        record.date = data.date
    if data.water_m3 is not None:
        record.water_m3 = data.water_m3
    if data.expense_id is not None:
        record.expense_id = data.expense_id
    else:
        # Allow explicitly clearing the expense_id
        if "expense_id" in data.model_fields_set:
            record.expense_id = None
    if data.notes is not None:
        record.notes = data.notes
    elif "notes" in data.model_fields_set:
        record.notes = None
    await db.flush()
    await sync_plot_event_from_irrigation(db, record)
    return record


async def delete_irrigation_record(
    db: AsyncSession, record_id: int, user_id: int
) -> None:
    from app.services.plot_events_service import delete_plot_event_for_irrigation

    record = await get_irrigation_record(db, record_id, user_id)
    if record is not None:
        await delete_plot_event_for_irrigation(db, record_id, user_id)
        await db.delete(record)
        await db.flush()

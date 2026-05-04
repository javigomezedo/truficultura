from __future__ import annotations

import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.well import Well
from app.schemas.plot_event import EventType, PlotEventCreate, PlotEventUpdate

ONE_TIME_EVENT_TYPES = {EventType.VALLADO, EventType.INSTALLED_DRIP}


def _now_utc() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _is_recurring_by_type(event_type: EventType) -> bool:
    return event_type not in ONE_TIME_EVENT_TYPES


async def validate_plot_ownership(db: AsyncSession, plot_id: int, tenant_id: int) -> None:
    result = await db.execute(
        select(Plot.id).where(Plot.id == plot_id, Plot.tenant_id == tenant_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Parcela no encontrada"),
        )


async def validate_one_time_event(
    db: AsyncSession,
    *,
    plot_id: int,
    tenant_id: int,
    event_type: EventType,
    exclude_event_id: Optional[int] = None,
) -> None:
    if event_type not in ONE_TIME_EVENT_TYPES:
        return

    stmt = select(PlotEvent).where(
        PlotEvent.tenant_id == tenant_id,
        PlotEvent.plot_id == plot_id,
        PlotEvent.event_type == event_type.value,
    )
    if exclude_event_id is not None:
        stmt = stmt.where(PlotEvent.id != exclude_event_id)

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("Este evento solo puede registrarse una vez por parcela"),
        )


async def create_plot_event(
    db: AsyncSession, tenant_id: int, data: PlotEventCreate, acting_user_id: Optional[int] = None
) -> PlotEvent:
    await validate_plot_ownership(db, data.plot_id, tenant_id)
    await validate_one_time_event(
        db,
        plot_id=data.plot_id,
        tenant_id=tenant_id,
        event_type=data.event_type,
    )

    event = PlotEvent(
        tenant_id=tenant_id,
        created_by_user_id=acting_user_id,
        plot_id=data.plot_id,
        event_type=data.event_type.value,
        date=data.date,
        notes=data.notes,
        is_recurring=(
            data.is_recurring
            if data.is_recurring is not None
            else _is_recurring_by_type(data.event_type)
        ),
        created_at=_now_utc(),
        updated_at=_now_utc(),
    )
    db.add(event)
    await db.flush()
    return event


async def get_plot_event(
    db: AsyncSession, event_id: int, tenant_id: int
) -> Optional[PlotEvent]:
    result = await db.execute(
        select(PlotEvent).where(PlotEvent.id == event_id, PlotEvent.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_plot_events(
    db: AsyncSession,
    tenant_id: int,
    *,
    plot_id: Optional[int] = None,
    start_date: Optional[datetime.date] = None,
    end_date: Optional[datetime.date] = None,
    event_types: Optional[list[EventType]] = None,
) -> list[PlotEvent]:
    stmt = select(PlotEvent).where(PlotEvent.tenant_id == tenant_id)

    if plot_id is not None:
        stmt = stmt.where(PlotEvent.plot_id == plot_id)
    if start_date is not None:
        stmt = stmt.where(PlotEvent.date >= start_date)
    if end_date is not None:
        stmt = stmt.where(PlotEvent.date <= end_date)
    if event_types:
        stmt = stmt.where(
            PlotEvent.event_type.in_([event_type.value for event_type in event_types])
        )

    result = await db.execute(stmt.order_by(PlotEvent.date.desc(), PlotEvent.id.desc()))
    return result.scalars().all()


async def update_plot_event(
    db: AsyncSession, event: PlotEvent, data: PlotEventUpdate, acting_user_id: Optional[int] = None
) -> PlotEvent:
    new_event_type = (
        data.event_type if data.event_type is not None else EventType(event.event_type)
    )
    target_plot_id = event.plot_id

    await validate_one_time_event(
        db,
        plot_id=target_plot_id,
        tenant_id=event.tenant_id,
        event_type=new_event_type,
        exclude_event_id=event.id,
    )

    if data.event_type is not None:
        event.event_type = data.event_type.value
    if data.date is not None:
        event.date = data.date
    if data.notes is not None:
        event.notes = data.notes
    elif "notes" in data.model_fields_set:
        event.notes = None

    if data.is_recurring is not None:
        event.is_recurring = data.is_recurring
    else:
        event.is_recurring = _is_recurring_by_type(EventType(event.event_type))

    event.updated_at = _now_utc()
    event.updated_by_user_id = acting_user_id
    await db.flush()
    return event


async def delete_plot_event(db: AsyncSession, event_id: int, tenant_id: int) -> None:
    event = await get_plot_event(db, event_id, tenant_id)
    if event is None:
        return
    await db.delete(event)
    await db.flush()


async def sync_plot_event_from_irrigation(
    db: AsyncSession, irrigation_record: IrrigationRecord
) -> PlotEvent:
    result = await db.execute(
        select(PlotEvent).where(
            PlotEvent.related_irrigation_id == irrigation_record.id,
            PlotEvent.tenant_id == irrigation_record.tenant_id,
        )
    )
    event = result.scalar_one_or_none()

    if event is None:
        event = PlotEvent(
            tenant_id=irrigation_record.tenant_id,
            created_by_user_id=irrigation_record.created_by_user_id,
            plot_id=irrigation_record.plot_id,
            event_type=EventType.RIEGO.value,
            date=irrigation_record.date,
            notes=irrigation_record.notes,
            is_recurring=True,
            related_irrigation_id=irrigation_record.id,
            created_at=_now_utc(),
            updated_at=_now_utc(),
        )
        db.add(event)
    else:
        event.plot_id = irrigation_record.plot_id
        event.date = irrigation_record.date
        event.notes = irrigation_record.notes
        event.updated_at = _now_utc()

    await db.flush()
    return event


async def sync_plot_event_from_well(db: AsyncSession, well_record: Well) -> PlotEvent:
    result = await db.execute(
        select(PlotEvent).where(
            PlotEvent.related_well_id == well_record.id,
            PlotEvent.tenant_id == well_record.tenant_id,
        )
    )
    event = result.scalar_one_or_none()

    if event is None:
        event = PlotEvent(
            tenant_id=well_record.tenant_id,
            created_by_user_id=well_record.created_by_user_id,
            plot_id=well_record.plot_id,
            event_type=EventType.POZO.value,
            date=well_record.date,
            notes=well_record.notes,
            is_recurring=True,
            related_well_id=well_record.id,
            created_at=_now_utc(),
            updated_at=_now_utc(),
        )
        db.add(event)
    else:
        event.plot_id = well_record.plot_id
        event.date = well_record.date
        event.notes = well_record.notes
        event.updated_at = _now_utc()

    await db.flush()
    return event


async def delete_plot_event_for_irrigation(
    db: AsyncSession, irrigation_id: int, tenant_id: int
) -> None:
    result = await db.execute(
        select(PlotEvent).where(
            PlotEvent.related_irrigation_id == irrigation_id,
            PlotEvent.tenant_id == tenant_id,
        )
    )
    event = result.scalar_one_or_none()
    if event is None:
        return

    await db.delete(event)
    await db.flush()


async def delete_plot_event_for_well(
    db: AsyncSession, well_id: int, tenant_id: int
) -> None:
    result = await db.execute(
        select(PlotEvent).where(
            PlotEvent.related_well_id == well_id,
            PlotEvent.tenant_id == tenant_id,
        )
    )
    event = result.scalar_one_or_none()
    if event is None:
        return

    await db.delete(event)
    await db.flush()

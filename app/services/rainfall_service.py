from __future__ import annotations

import datetime
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.plot import Plot
from app.models.rainfall import RainfallRecord
from app.schemas.rainfall import RainfallCreate, RainfallUpdate
from app.utils import campaign_year


async def get_rainfall_record(
    db: AsyncSession, record_id: int, user_id: int
) -> Optional[RainfallRecord]:
    result = await db.execute(
        select(RainfallRecord).where(
            RainfallRecord.id == record_id,
            RainfallRecord.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def list_rainfall_records(
    db: AsyncSession,
    user_id: int,
    *,
    plot_id: Optional[int] = None,
    municipio_cod: Optional[str] = None,
    year: Optional[int] = None,
    source: Optional[str] = None,
) -> list[RainfallRecord]:
    stmt = select(RainfallRecord).where(RainfallRecord.user_id == user_id)
    if plot_id is not None:
        stmt = stmt.where(RainfallRecord.plot_id == plot_id)
    if municipio_cod is not None:
        stmt = stmt.where(RainfallRecord.municipio_cod == municipio_cod)
    if source is not None:
        stmt = stmt.where(RainfallRecord.source == source)

    records_result = await db.execute(stmt.order_by(RainfallRecord.date.desc()))
    records = records_result.scalars().all()

    if year is not None:
        records = [r for r in records if campaign_year(r.date) == year]

    return records


async def _get_all_years(db: AsyncSession, user_id: int) -> list[int]:
    result = await db.execute(
        select(RainfallRecord.date).where(RainfallRecord.user_id == user_id)
    )
    dates = result.scalars().all()
    return sorted({campaign_year(d) for d in dates}, reverse=True)


async def _get_user_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def _get_user_municipios(db: AsyncSession, user_id: int) -> list[dict]:
    result = await db.execute(
        select(RainfallRecord.municipio_cod, RainfallRecord.municipio_name)
        .where(
            RainfallRecord.user_id == user_id,
            RainfallRecord.municipio_cod.isnot(None),
        )
        .distinct()
        .order_by(RainfallRecord.municipio_cod)
    )
    rows = result.all()
    seen: dict[str, dict] = {}
    for cod, name in rows:
        if cod and cod not in seen:
            seen[cod] = {"cod": cod, "name": name or cod}
    return list(seen.values())


async def get_rainfall_list_context(
    db: AsyncSession,
    user_id: int,
    *,
    year: Optional[int] = None,
    plot_id: Optional[int] = None,
    source: Optional[str] = None,
    municipio_cod: Optional[str] = None,
    only_with_rain: bool = False,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    records = await list_rainfall_records(
        db,
        user_id,
        plot_id=plot_id,
        year=year,
        source=source,
        municipio_cod=municipio_cod,
    )
    if only_with_rain:
        records = [r for r in records if r.precipitation_mm > 0]
    plots = await _get_user_plots(db, user_id)
    years = await _get_all_years(db, user_id)
    municipios = await _get_user_municipios(db, user_id)

    _SORT_KEYS = {
        "date": lambda x: x.date,
        "plot": lambda x: x.plot.name if x.plot else x.municipio_cod or "",
        "precipitation_mm": lambda x: x.precipitation_mm,
        "source": lambda x: x.source,
    }
    key_fn = _SORT_KEYS.get(sort_by, lambda x: x.date)
    records = sorted(records, key=key_fn, reverse=(sort_order == "desc"))

    total_mm = sum(r.precipitation_mm for r in records)

    return {
        "records": records,
        "plots": plots,
        "years": years,
        "municipios": municipios,
        "selected_year": year,
        "selected_plot": plot_id,
        "selected_source": source,
        "selected_municipio": municipio_cod,
        "only_with_rain": only_with_rain,
        "total_mm": round(total_mm, 1),
        "count": len(records),
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


async def get_rainfall_for_plot_on_date(
    db: AsyncSession,
    plot: Plot,
    date: datetime.date,
    user_id: int,
) -> Optional[RainfallRecord]:
    """
    Devuelve el registro de lluvia para una parcela en una fecha concreta.
    Prioridad: registro con plot_id exacto > registro de municipio (plot_id=NULL).
    """
    # 1. Buscar registro específico de la parcela
    result = await db.execute(
        select(RainfallRecord).where(
            RainfallRecord.user_id == user_id,
            RainfallRecord.plot_id == plot.id,
            RainfallRecord.date == date,
        )
    )
    record = result.scalar_one_or_none()
    if record is not None:
        return record

    # 2. Fallback: registro a nivel de municipio
    if plot.municipio_cod:
        result = await db.execute(
            select(RainfallRecord).where(
                RainfallRecord.user_id == user_id,
                RainfallRecord.plot_id.is_(None),
                RainfallRecord.municipio_cod == plot.municipio_cod,
                RainfallRecord.date == date,
            )
        )
        return result.scalar_one_or_none()

    return None


async def create_rainfall_record(
    db: AsyncSession, user_id: int, data: RainfallCreate
) -> RainfallRecord:
    # Si se especifica plot_id, verificar que pertenece al usuario
    if data.plot_id is not None:
        plot_result = await db.execute(
            select(Plot).where(Plot.id == data.plot_id, Plot.user_id == user_id)
        )
        if plot_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_("Parcela no encontrada"),
            )

    record = RainfallRecord(
        user_id=user_id,
        plot_id=data.plot_id,
        municipio_cod=data.municipio_cod,
        date=data.date,
        precipitation_mm=data.precipitation_mm,
        source=data.source,
        notes=data.notes,
    )
    db.add(record)
    await db.flush()
    await db.refresh(record)
    return record


async def update_rainfall_record(
    db: AsyncSession, record_id: int, user_id: int, data: RainfallUpdate
) -> RainfallRecord:
    record = await get_rainfall_record(db, record_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Registro de lluvia no encontrado"),
        )

    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(record, field, value)

    await db.flush()
    await db.refresh(record)
    return record


async def delete_rainfall_record(
    db: AsyncSession, record_id: int, user_id: int
) -> None:
    record = await get_rainfall_record(db, record_id, user_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_("Registro de lluvia no encontrado"),
        )
    await db.delete(record)
    await db.flush()

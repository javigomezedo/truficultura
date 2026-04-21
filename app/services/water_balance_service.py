from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.models.rainfall import RainfallRecord


def liters_per_second_to_m3_per_hour(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return (value * 3600.0) / 1000.0


def precipitation_mm_to_m3(
    precipitation_mm: Optional[float], area_ha: Optional[float]
) -> Optional[float]:
    if precipitation_mm is None or area_ha is None:
        return None
    return precipitation_mm * area_ha * 10.0


async def get_rainfall_for_plot(
    db: AsyncSession,
    user_id: int,
    plot: Plot,
    target_date: datetime.date,
) -> tuple[Optional[RainfallRecord], str]:
    """Busca el registro de lluvia para la parcela en rainfall_records.

    Prioridad:
    1. Registro asociado directamente a la parcela (plot_id exacto).
    2. Cualquier registro de municipio (aemet o ibericam) cuyo municipio_cod
       coincida con el de la parcela (construyendo el código INE a 5 dígitos
       si fuera necesario).

    Devuelve (registro, fuente) donde fuente ∈ {"plot", "municipality", "none"}.
    """
    # 1. Registro específico de la parcela
    result = await db.execute(
        select(RainfallRecord).where(
            RainfallRecord.user_id == user_id,
            RainfallRecord.plot_id == plot.id,
            RainfallRecord.date == target_date,
        )
    )
    record = result.scalar_one_or_none()
    if record is not None:
        return record, "plot"

    # 2. Fallback por municipio (cualquier fuente: aemet, ibericam)
    municipio_cod = plot.municipio_cod
    if not municipio_cod:
        return None, "none"

    if plot.provincia_cod and len(municipio_cod) <= 3:
        municipio_cod = f"{plot.provincia_cod}{municipio_cod.zfill(3)}"

    result = await db.execute(
        select(RainfallRecord).where(
            RainfallRecord.user_id == user_id,
            RainfallRecord.plot_id.is_(None),
            RainfallRecord.municipio_cod == municipio_cod,
            RainfallRecord.date == target_date,
        )
    )
    record = result.scalar_one_or_none()
    if record is not None:
        return record, "municipality"
    return None, "none"


async def get_plot_daily_water_balance(
    db: AsyncSession,
    user_id: int,
    plot_id: int,
    target_date: datetime.date,
    *,
    is_forecast: bool = False,
) -> Optional[dict]:
    plot_result = await db.execute(
        select(Plot).where(Plot.id == plot_id, Plot.user_id == user_id)
    )
    plot = plot_result.scalar_one_or_none()
    if plot is None:
        return None

    irrigation_result = await db.execute(
        select(IrrigationRecord).where(
            IrrigationRecord.user_id == user_id,
            IrrigationRecord.plot_id == plot_id,
            IrrigationRecord.date == target_date,
        )
    )
    irrigation_records = irrigation_result.scalars().all()
    irrigation_m3 = round(sum(item.water_m3 for item in irrigation_records), 3)

    rainfall_record, rainfall_source = await get_rainfall_for_plot(
        db,
        user_id,
        plot,
        target_date,
    )
    precipitation_mm = (
        rainfall_record.precipitation_mm if rainfall_record is not None else None
    )
    rain_m3 = precipitation_mm_to_m3(precipitation_mm, plot.area_ha)
    total_water_m3 = irrigation_m3 + (rain_m3 or 0.0)

    return {
        "plot_id": plot.id,
        "plot_name": plot.name,
        "date": target_date,
        "is_forecast": is_forecast,
        "rainfall_source": rainfall_source,
        "precipitation_mm": precipitation_mm,
        "rain_m3": round(rain_m3, 3) if rain_m3 is not None else None,
        "irrigation_m3": irrigation_m3,
        "total_water_m3": round(total_water_m3, 3),
        "water_flow_lps": plot.water_flow_lps,
        "water_flow_m3_per_hour": liters_per_second_to_m3_per_hour(plot.water_flow_lps),
        "area_ha": plot.area_ha,
        "irrigation_events_count": len(irrigation_records),
        "quality_status": None,
    }

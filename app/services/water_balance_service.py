from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.models.rainfall import RainfallRecord
from app.services.rainfall_service import (
    resolve_municipio_cod,
    select_best_rainfall_per_day,
)

# Mínimo de campañas con datos por parcela para confiar en su umbral propio.
# Por debajo de este valor se usa el umbral global del usuario como fallback.
_MIN_PLOT_SAMPLE = 5


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
) -> tuple[Optional[float], str]:
    """Devuelve (precipitation_mm, source_label) para el mejor registro de lluvia
    de target_date aplicando la prioridad:
      "manual"   → registro con plot_id = plot.id
      "aemet"    → registro de municipio con source='aemet'
      "ibericam" → registro de municipio con source='ibericam'
      "none"     → sin datos

    Emite una sola query que carga tanto los registros directos de la parcela
    como los del municipio (si está configurado), y selecciona el mejor con
    select_best_rainfall_per_day.
    """
    municipio_cod = resolve_municipio_cod(plot)

    if municipio_cod:
        stmt = select(RainfallRecord).where(
            RainfallRecord.user_id == user_id,
            RainfallRecord.date == target_date,
            or_(
                RainfallRecord.plot_id == plot.id,
                and_(
                    RainfallRecord.plot_id.is_(None),
                    RainfallRecord.municipio_cod == municipio_cod,
                ),
            ),
        )
    else:
        stmt = select(RainfallRecord).where(
            RainfallRecord.user_id == user_id,
            RainfallRecord.date == target_date,
            RainfallRecord.plot_id == plot.id,
        )

    records = (await db.execute(stmt)).scalars().all()
    daily = select_best_rainfall_per_day(records, plot.id, municipio_cod)

    if target_date not in daily:
        return None, "none"

    mm, source_label = daily[target_date]
    return mm, source_label


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

    precipitation_mm, rainfall_source = await get_rainfall_for_plot(
        db,
        user_id,
        plot,
        target_date,
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
        "caudal_riego": plot.caudal_riego,
        "area_ha": plot.area_ha,
        "irrigation_events_count": len(irrigation_records),
        "quality_status": None,
    }


async def simulate_irrigation(
    db: AsyncSession,
    user_id: int,
    plot_id: int,
    sim_date: datetime.date,
) -> Optional[dict]:
    """Calcula si conviene regar en sim_date para plot_id comparando el agua
    acumulada en la campaña (riego + lluvia con prioridad de fuente) con la
    meseta detectada históricamente (detect_irrigation_thresholds).

    No persiste nada en BD.  Devuelve None si la parcela no existe o no pertenece
    al usuario.
    """
    from app.services.plot_analytics_service import detect_irrigation_thresholds
    from app.utils import campaign_year

    # 1. Cargar parcela
    plot_result = await db.execute(
        select(Plot).where(Plot.id == plot_id, Plot.user_id == user_id)
    )
    plot = plot_result.scalar_one_or_none()
    if plot is None:
        return None

    # 2. Rango de campaña
    cy = campaign_year(sim_date)
    campaign_start = datetime.date(cy, 5, 1)
    campaign_end = sim_date  # hasta el día de simulación inclusive

    # 3. Total riego acumulado en la campaña hasta sim_date
    irrig_result = await db.execute(
        select(IrrigationRecord).where(
            IrrigationRecord.user_id == user_id,
            IrrigationRecord.plot_id == plot_id,
            IrrigationRecord.date >= campaign_start,
            IrrigationRecord.date <= campaign_end,
        )
    )
    irrigation_m3 = round(sum(r.water_m3 for r in irrig_result.scalars().all()), 3)

    # 4. Total lluvia acumulada en la campaña hasta sim_date (con prioridad de fuente)
    municipio_cod = resolve_municipio_cod(plot)

    if municipio_cod:
        rain_stmt = select(RainfallRecord).where(
            RainfallRecord.user_id == user_id,
            RainfallRecord.date >= campaign_start,
            RainfallRecord.date <= campaign_end,
            or_(
                RainfallRecord.plot_id == plot_id,
                and_(
                    RainfallRecord.plot_id.is_(None),
                    RainfallRecord.municipio_cod == municipio_cod,
                ),
            ),
        )
    else:
        rain_stmt = select(RainfallRecord).where(
            RainfallRecord.user_id == user_id,
            RainfallRecord.date >= campaign_start,
            RainfallRecord.date <= campaign_end,
            RainfallRecord.plot_id == plot_id,
        )

    rain_records = (await db.execute(rain_stmt)).scalars().all()
    daily_rain = select_best_rainfall_per_day(rain_records, plot_id, municipio_cod)

    total_rain_mm = sum(mm for mm, _ in daily_rain.values())
    rain_m3 = round(precipitation_mm_to_m3(total_rain_mm, plot.area_ha) or 0.0, 3)

    # 5. Meseta histórica — primero por parcela (≥_MIN_PLOT_SAMPLE campañas), fallback global
    thresholds = await detect_irrigation_thresholds(db, user_id, plot_ids=[plot_id])
    if thresholds.get("status") == "ok" and thresholds.get("sample_size", 0) >= _MIN_PLOT_SAMPLE:
        threshold_scope: Optional[str] = "plot"
    else:
        thresholds = await detect_irrigation_thresholds(db, user_id)
        threshold_scope = "global" if thresholds.get("status") == "ok" else None
    plateau_status = thresholds.get("status")
    plateau_m3 = thresholds.get("plateau_start_m3")

    total_water_m3 = round(irrigation_m3 + rain_m3, 3)

    # 6. Recomendación
    if plateau_status != "ok":
        should_irrigate = None
        reason = "insufficient_data"
        remaining_m3 = None
        hours_needed = None
    elif plateau_m3 is None:
        should_irrigate = None
        reason = "no_plateau_detected"
        remaining_m3 = None
        hours_needed = None
    elif total_water_m3 >= plateau_m3:
        should_irrigate = False
        reason = "plateau_reached"
        remaining_m3 = 0.0
        hours_needed = 0.0
    else:
        should_irrigate = True
        reason = "below_plateau"
        remaining_m3 = round(plateau_m3 - total_water_m3, 3)
        hours_needed = (
            round(remaining_m3 / plot.caudal_riego, 2)
            if plot.caudal_riego
            else None
        )

    return {
        "plot_id": plot.id,
        "plot_name": plot.name,
        "date": sim_date.isoformat(),
        "campaign_year": cy,
        "irrigation_m3": irrigation_m3,
        "rain_mm": round(total_rain_mm, 1),
        "rain_m3": rain_m3,
        "rainfall_days_counted": len(daily_rain),
        "total_water_m3": total_water_m3,
        "plateau_start_m3": plateau_m3,
        "should_irrigate": should_irrigate,
        "remaining_m3": remaining_m3,
        "hours_needed": hours_needed,
        "caudal_riego": plot.caudal_riego,
        "reason": reason,
        "sample_size": thresholds.get("sample_size"),
        "threshold_scope": threshold_scope,
    }

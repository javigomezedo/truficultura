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
from app.services.ibericam_service import MUNICIPIO_COD_TO_NAME
from app.utils import campaign_year

# Prioridad de fuente: menor número = mayor prioridad.
# 0: registro manual directo de la parcela (plot_id asignado)
# 1: municipio vía AEMET
# 2: municipio vía Ibericam
_SOURCE_PRIORITY: dict[str, int] = {"aemet": 1, "ibericam": 2}
_PRIORITY_SOURCE: dict[int, str] = {v: k for k, v in _SOURCE_PRIORITY.items()}


def resolve_municipio_cod(plot: Plot) -> Optional[str]:
    """Devuelve el código INE de municipio normalizado a 5 dígitos, o None."""
    municipio_cod = plot.municipio_cod
    if not municipio_cod:
        return None
    if plot.provincia_cod and len(municipio_cod) <= 3:
        return f"{plot.provincia_cod}{municipio_cod.zfill(3)}"
    return municipio_cod


def _full_municipio_cod(provincia_cod: Optional[str], municipio_cod: Optional[str]) -> Optional[str]:
    """Igual que resolve_municipio_cod pero acepta strings sueltos."""
    if not municipio_cod:
        return None
    if provincia_cod and len(municipio_cod) <= 3:
        return f"{provincia_cod}{municipio_cod.zfill(3)}"
    return municipio_cod


def select_best_rainfall_per_day(
    records: list[RainfallRecord],
    plot_id: int,
    municipio_cod: Optional[str],
) -> dict[datetime.date, tuple[float, str]]:
    """Dado un conjunto de RainfallRecords (mezcla de parcela y municipio),
    devuelve {date: (precipitation_mm, source_label)} eligiendo el mejor
    registro por día según la prioridad:

      0 → "manual"  : registro con plot_id = plot_id (medición directa)
      1 → "aemet"   : registro de municipio con source='aemet'
      2 → "ibericam": registro de municipio con source='ibericam'

    Si hay varios registros a la misma prioridad en el mismo día, gana el primero.
    """
    best: dict[datetime.date, tuple[int, float]] = {}  # {date: (prio, mm)}

    for r in records:
        if r.plot_id == plot_id:
            prio = 0  # medición directa de la parcela
        elif r.plot_id is None and municipio_cod and r.municipio_cod == municipio_cod:
            prio = _SOURCE_PRIORITY.get(r.source, 99)
            if prio == 99:
                continue  # fuente desconocida
        else:
            continue  # no aplica a esta parcela

        current = best.get(r.date)
        if current is None or prio < current[0]:
            best[r.date] = (prio, r.precipitation_mm)

    return {
        d: (mm, "manual" if prio == 0 else _PRIORITY_SOURCE[prio])
        for d, (prio, mm) in best.items()
    }


async def get_rainfall_record(
    db: AsyncSession, record_id: int, user_id: int
) -> Optional[RainfallRecord]:
    """Devuelve el registro si pertenece al usuario O es compartido (user_id=NULL)."""
    from sqlalchemy import or_

    result = await db.execute(
        select(RainfallRecord).where(
            RainfallRecord.id == record_id,
            or_(
                RainfallRecord.user_id == user_id,
                RainfallRecord.user_id.is_(None),
            ),
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
    """Lista los registros de lluvia visibles para el usuario:
    - Registros manuales del usuario (user_id == X)
    - Registros compartidos AEMET/Ibericam (user_id IS NULL) de los municipios
      de las parcelas del usuario.
    """
    from sqlalchemy import and_, or_

    # Obtener los municipio_cod de las parcelas del usuario para filtrar shared records.
    # Normalizar a código INE de 5 dígitos (misma lógica que resolve_municipio_cod).
    plots_result = await db.execute(
        select(Plot.provincia_cod, Plot.municipio_cod)
        .where(
            Plot.user_id == user_id,
            Plot.municipio_cod.isnot(None),
            Plot.municipio_cod != "",
        )
        .distinct()
    )
    user_municipio_cods = list({
        full for row in plots_result.all()
        if (full := _full_municipio_cod(row.provincia_cod, row.municipio_cod))
    })

    if user_municipio_cods:
        visibility_clause = or_(
            RainfallRecord.user_id == user_id,
            and_(
                RainfallRecord.user_id.is_(None),
                RainfallRecord.municipio_cod.in_(user_municipio_cods),
            ),
        )
    else:
        visibility_clause = RainfallRecord.user_id == user_id

    stmt = select(RainfallRecord).where(visibility_clause)

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
    from sqlalchemy import and_, or_

    plots_result = await db.execute(
        select(Plot.provincia_cod, Plot.municipio_cod)
        .where(
            Plot.user_id == user_id,
            Plot.municipio_cod.isnot(None),
            Plot.municipio_cod != "",
        )
        .distinct()
    )
    user_municipio_cods = list({
        full for row in plots_result.all()
        if (full := _full_municipio_cod(row.provincia_cod, row.municipio_cod))
    })

    if user_municipio_cods:
        clause = or_(
            RainfallRecord.user_id == user_id,
            and_(
                RainfallRecord.user_id.is_(None),
                RainfallRecord.municipio_cod.in_(user_municipio_cods),
            ),
        )
    else:
        clause = RainfallRecord.user_id == user_id

    result = await db.execute(select(RainfallRecord.date).where(clause))
    dates = result.scalars().all()
    return sorted({campaign_year(d) for d in dates}, reverse=True)


async def _get_user_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def _get_user_municipios(db: AsyncSession, user_id: int) -> list[dict]:
    """Devuelve los municipios de las parcelas del usuario, enriquecidos con el
    nombre resuelto desde los registros de lluvia compartidos o el dict de ibericam."""
    # 1. Municipio_cod de parcelas del usuario (normalizado a 5 dígitos).
    plots_result = await db.execute(
        select(Plot.provincia_cod, Plot.municipio_cod)
        .where(
            Plot.user_id == user_id,
            Plot.municipio_cod.isnot(None),
            Plot.municipio_cod != "",
        )
        .distinct()
    )
    plot_cods = {
        full for row in plots_result.all()
        if (full := _full_municipio_cod(row.provincia_cod, row.municipio_cod))
    }

    if not plot_cods:
        return []

    # 2. Buscar nombres en rainfall_records compartidos
    names_result = await db.execute(
        select(RainfallRecord.municipio_cod, RainfallRecord.municipio_name)
        .where(
            RainfallRecord.user_id.is_(None),
            RainfallRecord.municipio_cod.in_(plot_cods),
            RainfallRecord.municipio_name.isnot(None),
        )
        .distinct()
    )
    name_map: dict[str, str] = {}
    for cod, name in names_result.all():
        if cod not in name_map and name:
            name_map[cod] = name

    seen: dict[str, str] = {}
    for cod in sorted(plot_cods):
        seen[cod] = name_map.get(cod) or MUNICIPIO_COD_TO_NAME.get(cod) or cod
    return [{"cod": cod, "name": name} for cod, name in seen.items()]


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
        "municipio_cod_to_name": MUNICIPIO_COD_TO_NAME,
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

    # 2. Fallback: registro a nivel de municipio (manual del usuario o compartido)
    if plot.municipio_cod:
        from sqlalchemy import or_

        result = await db.execute(
            select(RainfallRecord).where(
                or_(
                    RainfallRecord.user_id == user_id,
                    RainfallRecord.user_id.is_(None),
                ),
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
    # Solo se pueden crear registros manuales desde la UI de usuario
    if data.source != "manual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=_("Solo se pueden crear registros de tipo manual"),
        )
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
    if record.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_(
                "Los registros compartidos (AEMET/Ibericam) no se pueden modificar"
            ),
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
    if record.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_(
                "Los registros compartidos (AEMET/Ibericam) no se pueden eliminar"
            ),
        )
    await db.delete(record)
    await db.flush()


# ---------------------------------------------------------------------------
# Calendario de lluvia
# ---------------------------------------------------------------------------

_MONTH_NAMES_ES = [
    "",
    "Enero",
    "Febrero",
    "Marzo",
    "Abril",
    "Mayo",
    "Junio",
    "Julio",
    "Agosto",
    "Septiembre",
    "Octubre",
    "Noviembre",
    "Diciembre",
]
_DAY_LABELS = ["L", "M", "X", "J", "V", "S", "D"]


def _build_calendar_months(
    year: int,
    rain_by_date: dict[datetime.date, float],
    area_ha: Optional[float] = None,
) -> list[dict]:
    """
    Construye la lista de 12 meses (Mayo-Abril) para el calendario de campaña.
    Cada mes incluye: nombre, año calendario, total_mm, rain_days y una lista
    de semanas donde cada semana es una lista de 7 elementos (None o dict con
    day, mm, css_class).
    """
    # Campaña: Mayo year → Abril year+1
    campaign_months_order = [
        (year, 5),
        (year, 6),
        (year, 7),
        (year, 8),
        (year, 9),
        (year, 10),
        (year, 11),
        (year, 12),
        (year + 1, 1),
        (year + 1, 2),
        (year + 1, 3),
        (year + 1, 4),
    ]

    months = []
    for cal_year, month in campaign_months_order:
        import calendar

        first_weekday, num_days = calendar.monthrange(cal_year, month)
        # first_weekday: 0=Lunes … 6=Domingo (ISO)

        days_flat: list[dict | None] = [None] * first_weekday
        month_total = 0.0
        month_total_m3 = 0.0
        rain_days = 0

        for day_num in range(1, num_days + 1):
            d = datetime.date(cal_year, month, day_num)
            mm = rain_by_date.get(d, 0.0)
            month_total += mm
            if mm > 0:
                rain_days += 1

            if mm == 0:
                css = "rain-none"
            elif mm <= 5:
                css = "rain-low"
            elif mm <= 15:
                css = "rain-moderate"
            elif mm <= 30:
                css = "rain-heavy"
            else:
                css = "rain-very-heavy"

            m3: Optional[float] = None
            if area_ha is not None:
                m3 = round(mm * area_ha * 10, 1)
                month_total_m3 += mm * area_ha * 10

            days_flat.append({"day": day_num, "mm": mm, "m3": m3, "css": css})

        # Rellenar hasta completar la última semana
        remainder = len(days_flat) % 7
        if remainder:
            days_flat += [None] * (7 - remainder)

        weeks = [days_flat[i : i + 7] for i in range(0, len(days_flat), 7)]

        months.append(
            {
                "year": cal_year,
                "month": month,
                "name": _MONTH_NAMES_ES[month],
                "weeks": weeks,
                "total_mm": round(month_total, 1),
                "total_m3": round(month_total_m3, 1) if area_ha is not None else None,
                "rain_days": rain_days,
            }
        )

    return months


async def get_rainfall_calendar_context(
    db: AsyncSession,
    user_id: int,
    *,
    year: int,
    plot_id: Optional[int] = None,
    municipio_cod: Optional[str] = None,
    source: Optional[str] = None,
) -> dict:
    """
    Devuelve el contexto necesario para renderizar el calendario de lluvia
    de una campaña agrícola (Mayo-Abril).

    Si se filtra por parcela, se usan solo sus registros manuales.
    Si se filtra por municipio, se usan solo sus registros de municipio.
    Sin filtro se usan todos los registros del usuario para ese año.
    """
    records = await list_rainfall_records(
        db,
        user_id,
        plot_id=plot_id,
        municipio_cod=municipio_cod,
        source=source,
        year=year,
    )

    # Agregar por fecha: si hay varios registros en el mismo día, sumar mm.
    # (Para el calendario la suma tiene más sentido que elegir el mejor.)
    rain_by_date: dict[datetime.date, float] = {}
    for r in records:
        rain_by_date[r.date] = rain_by_date.get(r.date, 0.0) + r.precipitation_mm

    # Área de la parcela para convertir mm → m³ (solo cuando hay parcela filtrada)
    area_ha: Optional[float] = None
    if plot_id is not None:
        plot_result = await db.execute(
            select(Plot).where(Plot.id == plot_id, Plot.user_id == user_id)
        )
        plot_obj = plot_result.scalar_one_or_none()
        if plot_obj is not None and plot_obj.area_ha:
            area_ha = plot_obj.area_ha

    months = _build_calendar_months(year, rain_by_date, area_ha=area_ha)
    total_mm = round(sum(m["total_mm"] for m in months), 1)
    total_m3 = (
        round(sum(m["total_m3"] for m in months if m["total_m3"] is not None), 1)
        if area_ha is not None
        else None
    )
    rain_days = sum(m["rain_days"] for m in months)

    plots = await _get_user_plots(db, user_id)
    years = await _get_all_years(db, user_id)
    municipios = await _get_user_municipios(db, user_id)

    return {
        "months": months,
        "day_labels": _DAY_LABELS,
        "total_mm": total_mm,
        "total_m3": total_m3,
        "area_ha": area_ha,
        "rain_days": rain_days,
        "selected_year": year,
        "selected_plot": plot_id,
        "selected_municipio": municipio_cod,
        "selected_source": source,
        "plots": plots,
        "years": years,
        "municipios": municipios,
        "municipio_cod_to_name": MUNICIPIO_COD_TO_NAME,
    }

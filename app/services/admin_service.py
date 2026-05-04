"""Servicios de administración: resumen de lluvia compartida por municipio."""
from __future__ import annotations

import datetime
import json
import pathlib
from functools import lru_cache
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Plot
from app.models.rainfall import RainfallRecord
from app.services.ibericam_service import MUNICIPIO_COD_TO_NAME

_GEO_JSON = pathlib.Path(__file__).parent.parent / "static" / "js" / "municipios_geo.json"


@lru_cache(maxsize=1)
def _build_geo_name_map() -> dict[str, str]:
    """Construye {código_INE_5_dígitos: nombre} a partir de municipios_geo.json."""
    try:
        data = json.loads(_GEO_JSON.read_text(encoding="utf-8"))
        result: dict[str, str] = {}
        for prov_code, munis in data.get("municipalities", {}).items():
            for m in munis:
                ine = m.get("ine_code", "")
                name = m.get("name", "")
                if ine and name:
                    full_cod = f"{prov_code}{ine.zfill(3)}"
                    result[full_cod] = name.title()
        return result
    except Exception:
        return {}


def _normalize_municipio_cod(provincia_cod: Optional[str], municipio_cod: str) -> str:
    """Normaliza a código INE de 5 dígitos igual que resolve_municipio_cod(plot)."""
    if provincia_cod and len(municipio_cod) <= 3:
        return f"{provincia_cod}{municipio_cod.zfill(3)}"
    return municipio_cod


async def get_admin_rainfall_overview(db: AsyncSession) -> list[dict]:
    """Devuelve un resumen por municipio con el nº de parcelas y el rango de
    fechas disponible para AEMET e Ibericam (registros compartidos user_id=NULL).
    Solo se incluyen municipios que tengan al menos una parcela (cualquier usuario).
    """
    # 1. Parcelas por municipio (todos los usuarios).
    # Obtener provincia_cod + municipio_cod para normalizar a código INE de 5 dígitos.
    plots_q = await db.execute(
        select(Plot.provincia_cod, Plot.municipio_cod, func.count(Plot.id).label("num_plots"))
        .where(Plot.municipio_cod.isnot(None), Plot.municipio_cod != "")
        .group_by(Plot.provincia_cod, Plot.municipio_cod)
    )
    plots_by_municipio: dict[str, int] = {}
    for row in plots_q.all():
        full_cod = _normalize_municipio_cod(row.provincia_cod, row.municipio_cod)
        plots_by_municipio[full_cod] = plots_by_municipio.get(full_cod, 0) + row.num_plots

    if not plots_by_municipio:
        return []

    municipio_cods = list(plots_by_municipio.keys())

    # 2. Rango de fechas AEMET compartidas
    aemet_q = await db.execute(
        select(
            RainfallRecord.municipio_cod,
            func.min(RainfallRecord.date).label("desde"),
            func.max(RainfallRecord.date).label("hasta"),
        )
        .where(
            RainfallRecord.source == "aemet",
            RainfallRecord.tenant_id.is_(None),
            RainfallRecord.municipio_cod.in_(municipio_cods),
        )
        .group_by(RainfallRecord.municipio_cod)
    )
    aemet_ranges: dict[str, tuple[Optional[datetime.date], Optional[datetime.date]]] = {
        row.municipio_cod: (row.desde, row.hasta) for row in aemet_q.all()
    }

    # 3. Rango de fechas Ibericam compartidas
    ibericam_q = await db.execute(
        select(
            RainfallRecord.municipio_cod,
            func.min(RainfallRecord.date).label("desde"),
            func.max(RainfallRecord.date).label("hasta"),
        )
        .where(
            RainfallRecord.source == "ibericam",
            RainfallRecord.tenant_id.is_(None),
            RainfallRecord.municipio_cod.in_(municipio_cods),
        )
        .group_by(RainfallRecord.municipio_cod)
    )
    ibericam_ranges: dict[str, tuple[Optional[datetime.date], Optional[datetime.date]]] = {
        row.municipio_cod: (row.desde, row.hasta) for row in ibericam_q.all()
    }

    # 4. Nombres de municipios (de registros compartidos si existen, si no del dict)
    names_q = await db.execute(
        select(RainfallRecord.municipio_cod, RainfallRecord.municipio_name)
        .where(
            RainfallRecord.tenant_id.is_(None),
            RainfallRecord.municipio_cod.in_(municipio_cods),
            RainfallRecord.municipio_name.isnot(None),
        )
        .distinct()
    )
    name_map: dict[str, str] = {}
    for row in names_q.all():
        if row.municipio_cod not in name_map and row.municipio_name:
            name_map[row.municipio_cod] = row.municipio_name

    overview = []
    geo_names = _build_geo_name_map()
    for cod in sorted(municipio_cods):
        aemet = aemet_ranges.get(cod, (None, None))
        ibericam = ibericam_ranges.get(cod, (None, None))
        overview.append(
            {
                "municipio_cod": cod,
                "municipio_name": (
                    name_map.get(cod)
                    or MUNICIPIO_COD_TO_NAME.get(cod)
                    or geo_names.get(cod)
                    or cod
                ),
                "num_plots": plots_by_municipio[cod],
                "aemet_desde": aemet[0],
                "aemet_hasta": aemet[1],
                "ibericam_desde": ibericam[0],
                "ibericam_hasta": ibericam[1],
            }
        )
    return overview

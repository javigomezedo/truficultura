#!/usr/bin/env python3
"""
Cron script: importa datos de lluvia (AEMET e Ibericam) para todos los municipios
con parcelas registradas en el sistema.

Uso:
    uv run scripts/import_rainfall_cron.py
    uv run scripts/import_rainfall_cron.py --dry-run   # muestra qué haría sin escribir nada

Variables de entorno requeridas:
    DATABASE_URL   — URL de conexión a PostgreSQL (igual que en .env)
    AEMET_API_KEY  — Clave de la API AEMET (si se usa AEMET)

Lógica de prioridad (por municipio):
  1. Se descarga el inventario de estaciones AEMET para la provincia de la
     parcela y se busca si alguna estación coincide en nombre con el municipio.
     Si hay coincidencia → se importa desde AEMET.
  2. Si no hay estación AEMET, se descarga el sitemap de Ibericam y se busca
     si existe una estación cuyo slug coincida con el nombre del municipio.
     Si hay coincidencia → se importa desde Ibericam.
  3. Si no hay ninguna fuente disponible, el municipio se omite.

El descubrimiento es dinámico en cada ejecución del cron: no hay dicts
hardcodeados de mapeos. Esto permite que nuevas estaciones de AEMET o
Ibericam sean detectadas automáticamente.
"""

import argparse
import asyncio
import datetime
import logging
import os
import re
import sys
import unicodedata

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Asegura que el directorio raíz del proyecto está en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.plot import Plot
from app.models.rainfall import RainfallRecord
from app.services.aemet_service import (
    AemetClient,
    find_aemet_station_for_municipio,
    import_aemet_rainfall,
    normalize_station_name,
)
from app.services.ibericam_service import (
    IBERICAM_SITEMAP_URL,
    MUNICIPIO_COD_TO_NAME,
    _NON_STATION_SLUGS,
    import_ibericam_rainfall,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Normalización de nombres
# ---------------------------------------------------------------------------
# Reutilizamos la función del service para evitar duplicación.
_normalize = normalize_station_name


# ---------------------------------------------------------------------------
# Descubrimiento de fuentes
# ---------------------------------------------------------------------------


def find_aemet_station(
    all_stations: list[dict],
    municipio_cod: str,
    municipio_name: str,
) -> str | None:
    """Delegado a find_aemet_station_for_municipio del service."""
    return find_aemet_station_for_municipio(all_stations, municipio_cod, municipio_name)


async def fetch_ibericam_slugs() -> set[str]:
    """Descarga el sitemap de Ibericam y devuelve el conjunto de slugs de
    estaciones (descartando slugs que corresponden a categorías/regiones).
    """
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        resp = await client.get(IBERICAM_SITEMAP_URL)
        resp.raise_for_status()
        xml_text = resp.text

    slugs = re.findall(r"/lugar_webcam_el_tiempo/([^/<]+)/", xml_text)
    return {s for s in slugs if s not in _NON_STATION_SLUGS}


def find_ibericam_slug(
    sitemap_slugs: set[str],
    municipio_name: str,
) -> str | None:
    """Devuelve el slug de Ibericam si el sitemap contiene una estación
    cuyo slug coincide con el nombre normalizado del municipio.

    Ejemplo: 'Sarrión' → 'sarrion' → busca 'sarrion' en sitemap_slugs.
    """
    candidate = _normalize(municipio_name)
    if candidate in sitemap_slugs:
        return candidate
    return None


# ---------------------------------------------------------------------------
# Consulta a la DB
# ---------------------------------------------------------------------------


async def get_municipios_with_plots(session: AsyncSession) -> list[str]:
    """Devuelve todos los códigos INE de municipio (5 dígitos) de las parcelas del sistema.

    Aplica la misma lógica que ``resolve_municipio_cod(plot)``:
    si municipio_cod tiene ≤ 3 dígitos y hay provincia_cod, los combina
    (p.ej. provincia_cod="44", municipio_cod="210" → "44210").
    """
    result = await session.execute(
        select(Plot.provincia_cod, Plot.municipio_cod)
        .where(Plot.municipio_cod.isnot(None))
        .distinct()
    )
    seen: set[str] = set()
    for row in result.all():
        if not row.municipio_cod:
            continue
        if row.provincia_cod and len(row.municipio_cod) <= 3:
            full_cod = f"{row.provincia_cod}{row.municipio_cod.zfill(3)}"
        else:
            full_cod = row.municipio_cod
        seen.add(full_cod)
    return sorted(seen)


async def get_municipio_names(
    session: AsyncSession,
    municipio_cods: list[str],
) -> dict[str, str]:
    """Devuelve {municipio_cod: nombre} combinando la fuente más fiable:
    1. MUNICIPIO_COD_TO_NAME (mapeado desde slugs de Ibericam)
    2. RainfallRecord.municipio_name ya almacenado en la BD
    """
    # Partimos del dict estático
    names: dict[str, str] = {
        cod: MUNICIPIO_COD_TO_NAME[cod]
        for cod in municipio_cods
        if cod in MUNICIPIO_COD_TO_NAME
    }

    # Rellenamos los que faltan desde la BD
    missing = [cod for cod in municipio_cods if cod not in names]
    if missing:
        result = await session.execute(
            select(RainfallRecord.municipio_cod, RainfallRecord.municipio_name)
            .where(
                RainfallRecord.municipio_cod.in_(missing),
                RainfallRecord.municipio_name.isnot(None),
            )
            .distinct()
        )
        for row in result.all():
            if row.municipio_name and row.municipio_cod not in names:
                names[row.municipio_cod] = row.municipio_name

    return names


# ---------------------------------------------------------------------------
# Importación de un municipio
# ---------------------------------------------------------------------------


async def import_municipio(
    session: AsyncSession,
    municipio_cod: str,
    municipio_name: str,
    date_from: datetime.date,
    date_to: datetime.date,
    all_aemet_stations: list[dict],
    ibericam_slugs: set[str],
    *,
    dry_run: bool = False,
) -> None:
    """Importa lluvia para un municipio con prioridad exclusiva:
    1. AEMET si la provincia tiene una estación cuyo nombre coincide con el municipio.
    2. Ibericam si el sitemap contiene un slug que coincide con el municipio.
    3. Sin fuente → se omite el municipio.

    Con dry_run=True muestra qué haría sin escribir nada en la BD.
    """
    # --- Prioridad 1: AEMET ---
    aemet_indicativo = find_aemet_station(
        all_aemet_stations, municipio_cod, municipio_name
    )

    if aemet_indicativo:
        if dry_run:
            log.info(
                "[DRY-RUN] AEMET %s (%s) → estación=%s (rango %s → %s)",
                municipio_cod,
                municipio_name,
                aemet_indicativo,
                date_from,
                date_to,
            )
            return
        try:
            stats = await import_aemet_rainfall(
                session,
                municipio_cod=municipio_cod,
                municipio_name=municipio_name,
                station_code=aemet_indicativo,
                date_from=date_from,
                date_to=date_to,
            )
            log.info(
                "AEMET %s (%s) estación=%s: creados=%s actualizados=%s",
                municipio_cod,
                municipio_name,
                aemet_indicativo,
                stats.get("created", 0),
                stats.get("updated", 0),
            )
        except Exception as exc:
            log.error("AEMET %s: ERROR — %s", municipio_cod, exc)
        return

    # --- Prioridad 2: Ibericam ---
    ibericam_slug = find_ibericam_slug(ibericam_slugs, municipio_name)

    if ibericam_slug:
        if dry_run:
            log.info(
                "[DRY-RUN] Ibericam %s (%s) → slug=%s (mes %s/%s)",
                municipio_cod,
                municipio_name,
                ibericam_slug,
                date_to.month,
                date_to.year,
            )
            return
        today = date_to
        try:
            stats = await import_ibericam_rainfall(
                session,
                station_slug=ibericam_slug,
                municipio_cod=municipio_cod,
                municipio_name=municipio_name,
                year=today.year,
                month=today.month,
            )
            log.info(
                "Ibericam %s (%s) slug=%s: creados=%s actualizados=%s",
                municipio_cod,
                municipio_name,
                ibericam_slug,
                stats.get("created", 0),
                stats.get("updated", 0),
            )
        except Exception as exc:
            log.error("Ibericam %s: ERROR — %s", municipio_cod, exc)
        return

    # --- Sin fuente ---
    log.warning(
        "Municipio %s (%s): sin estación AEMET ni slug Ibericam. Se omite.",
        municipio_cod,
        municipio_name,
    )


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------


async def main(dry_run: bool = False) -> None:
    log.info("=== Cron lluvia: inicio ===")
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL no definida. Abortando.")
        sys.exit(1)

    # Reutilizamos la normalización de config.py que ya maneja:
    # postgres:// → postgresql+asyncpg://, sslmode= → ssl=, etc.
    from app.config import Settings

    settings = Settings(DATABASE_URL=database_url)
    database_url = settings.SQLALCHEMY_DATABASE_URL

    engine = create_async_engine(database_url, echo=False, pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    # ------------------------------------------------------------------
    # 1. Descargar inventario de estaciones AEMET (una sola vez por ejecución)
    # ------------------------------------------------------------------
    all_aemet_stations: list[dict] = []
    try:
        aemet_client = AemetClient()
        all_aemet_stations = await aemet_client.fetch_dataset(
            "/valores/climatologicos/inventarioestaciones/todasestaciones"
        )
        log.info(
            "AEMET: inventario descargado (%d estaciones)", len(all_aemet_stations)
        )
    except Exception as exc:
        log.warning(
            "AEMET: no se pudo obtener inventario de estaciones (%s). Se omitirá AEMET.",
            exc,
        )

    # ------------------------------------------------------------------
    # 2. Descargar slugs del sitemap de Ibericam (una sola vez por ejecución)
    # ------------------------------------------------------------------
    ibericam_slugs: set[str] = set()
    try:
        ibericam_slugs = await fetch_ibericam_slugs()
        log.info(
            "Ibericam: sitemap descargado (%d slugs de estaciones)", len(ibericam_slugs)
        )
    except Exception as exc:
        log.warning(
            "Ibericam: no se pudo obtener sitemap (%s). Se omitirá Ibericam.", exc
        )

    # ------------------------------------------------------------------
    # 3. Procesar cada municipio con parcelas
    # ------------------------------------------------------------------
    # Obtener la lista de municipios y sus nombres con una sesión temporal.
    async with async_session() as session:
        municipio_cods = await get_municipios_with_plots(session)
        if not municipio_cods:
            log.info("No hay municipios con parcelas. Nada que importar.")
            await engine.dispose()
            return
        municipio_names = await get_municipio_names(session, municipio_cods)

    log.info("Municipios a procesar: %s", municipio_cods)

    if dry_run:
        log.info(
            "[DRY-RUN] Modo simulación activado — no se escribirá nada en la BD."
        )

    # Cada municipio se procesa con su propia sesión y commit independiente.
    # Así, si la conexión cae durante los reintentos HTTP de un municipio
    # (p.ej. ibericam 500 × 3 con backoff exponencial), los demás no se ven
    # afectados y la sesión comienza fresca con pool_pre_ping=True.
    for municipio_cod in municipio_cods:
        municipio_name = municipio_names.get(municipio_cod) or municipio_cod
        try:
            async with async_session() as session:
                await import_municipio(
                    session,
                    municipio_cod,
                    municipio_name,
                    yesterday,
                    today,
                    all_aemet_stations,
                    ibericam_slugs,
                    dry_run=dry_run,
                )
                if not dry_run:
                    await session.commit()
        except Exception as exc:
            log.error(
                "Error inesperado procesando municipio %s (%s): %s",
                municipio_cod,
                municipio_name,
                exc,
            )

    if dry_run:
        log.info("[DRY-RUN] Simulación completada. No se ha escrito nada.")
    else:
        log.info("Importación completada.")

    await engine.dispose()
    log.info("=== Cron lluvia: fin ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Importa lluvia (AEMET / Ibericam) para todos los municipios con parcelas."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué importaría sin escribir nada en la base de datos.",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))

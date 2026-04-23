"""Servicio de integración con ibericam.com para importar precipitación diaria.

El endpoint descubierto es:
    POST https://ibericam.com/el-tiempo/rainDaily.php
    Content-Type: application/json; charset=UTF-8
    Body: {"station": "<slug>", "month": "MM", "year": "YYYY"}
          {"station": "<slug>", "now": "month"}   → mes en curso
          {"station": "<slug>", "now": "year"}    → año en curso

Respuesta: lista de objetos {"labels": "YYYY-MM-DD", "input": "0.0"}

Los registros se almacenan en `rainfall_records` (tabla de pluviómetro) con
source="ibericam" y plot_id=NULL (nivel municipio, usando municipio_cod).
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
from typing import Any, Callable, Optional

import httpx
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rainfall import RainfallRecord

logger = logging.getLogger(__name__)

IBERICAM_RAIN_URL = "https://ibericam.com/el-tiempo/rainDaily.php"
IBERICAM_SITEMAP_URL = "https://ibericam.com/lugar_webcam_el_tiempo-sitemap.xml"
_IBERICAM_TIMEOUT = 30.0

# Slugs del sitemap que son categorías/regiones/etiquetas, no estaciones reales.
_NON_STATION_SLUGS: frozenset[str] = frozenset(
    {
        # Regiones / comunidades / provincias
        "aragon",
        "andalucia",
        "castilla-y-leon",
        "castilla-la-macha",
        "comunidad-valenciana",
        "galicia",
        "soria",
        "alicante",
        "burgos",
        "valencia",
        "provincia-a-coruna",
        "provincia-de-granada",
        "provincia-de-guadalajara",
        "provincia-de-huesca",
        "provincia-de-teruel",
        "provincia-de-valencia",
        # Categorías / etiquetas temáticas
        "webcam",
        "estacion-meteorologica",
        "el-tiempo",
        "categoria",
        "geografia",
        "paisaje",
        "montana",
        "pueblo",
        "ciudad",
        "plaza",
        "playa",
        "costa-azahar",
        "rio-turia",
        "sierra-de-albarracin",
        "sierra-de-gudar",
        "maestrazgo",
        "polos-del-frio",
        "iglesia",
        "ayuntamiento",
        "region",
        "granada-granada",
    }
)

# Mapeado slug ibericam → código municipio INE completo de 5 dígitos.
# Formato: provincia_cod (2 díg) + municipio_ine (3 díg con zero-pad).
# Este código es el que se almacena en RainfallRecord.municipio_cod y se obtiene
# a través de resolve_municipio_cod(plot). Los códigos SIGPAC (distintos en algunos
# municipios como Sarrión INE=44210/SIGPAC=44223) sólo se usan para el API de SIGPAC
# y se gestionan desde el JSON municipios_geo.json vía el formulario de parcelas.
IBERICAM_SLUG_TO_MUNICIPIO: dict[str, str] = {
    "sarrion": "44210",
    "albentosa": "44010",
    "alcala-de-la-selva": "44012",
    "san-agustin": "44206",
    "cabra-de-mora": "44048",
    "el-castellar": "44070",
    "formiche-alto": "44103",
    "gudar": "44121",
}


# ---------------------------------------------------------------------------
# HTTP helpers — inyectable en tests
# ---------------------------------------------------------------------------

HttpPostJson = Callable[[str, Any, float], Any]
HttpGetText = Callable[[str, float], str]


async def _default_post_json(url: str, body: Any, timeout: float) -> Any:
    """Realiza POST a url con body JSON; devuelve el payload parseado."""
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                timeout=timeout, follow_redirects=True
            ) as client:
                resp = await client.post(
                    url,
                    json=body,
                    headers={"Content-Type": "application/json; charset=UTF-8"},
                )
                resp.raise_for_status()
                return resp.json()
        except httpx.RequestError as exc:
            logger.warning("ibericam intento %d: %s", attempt + 1, exc)
            if attempt == 2:
                raise
    return None  # inalcanzable


async def _default_get_text(url: str, timeout: float) -> str:
    """Realiza GET y devuelve el cuerpo como texto."""
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.text


# ---------------------------------------------------------------------------
# Parseo de respuesta
# ---------------------------------------------------------------------------


def parse_ibericam_response(
    payload: Any,
) -> list[tuple[datetime.date, float]]:
    """Convierte la respuesta JSON de ibericam en lista de (fecha, mm).

    Filtra filas con fecha inválida o valor no parseable.
    Valores null/None → 0.0 mm.
    """
    if not isinstance(payload, list):
        return []

    out: list[tuple[datetime.date, float]] = []
    for row in payload:
        if not isinstance(row, dict):
            continue
        label = row.get("labels")
        raw_input = row.get("input")

        # Parsear fecha
        try:
            date = datetime.date.fromisoformat(str(label))
        except (TypeError, ValueError):
            logger.debug("ibericam: fecha inválida %r — fila ignorada", label)
            continue

        # Parsear mm
        if raw_input is None or str(raw_input).strip() == "":
            mm = 0.0
        else:
            try:
                mm = float(str(raw_input).replace(",", "."))
                if mm < 0:
                    mm = 0.0
            except (TypeError, ValueError):
                logger.debug("ibericam: valor inválido %r en %s — 0.0", raw_input, date)
                mm = 0.0

        out.append((date, mm))
    return out


# ---------------------------------------------------------------------------
# Fetch desde ibericam
# ---------------------------------------------------------------------------


async def get_daily_precipitation(
    station_slug: str,
    *,
    year: Optional[int] = None,
    month: Optional[int] = None,
    http_post_json: Optional[HttpPostJson] = None,
) -> list[tuple[datetime.date, float]]:
    """Descarga precipitación diaria de ibericam para la estación y período dados.

    - Si se pasan `year` y `month`: descarga ese mes concreto.
    - Si sólo se pasa `year`: descarga el año completo (now=year).
    - Si no se pasa nada: descarga el mes en curso (now=month).

    Devuelve lista de (date, precipitation_mm).
    """
    post_fn = http_post_json or _default_post_json
    body: dict[str, str] = {"station": station_slug}

    if year is not None and month is not None:
        body["month"] = f"{month:02d}"
        body["year"] = str(year)
    elif year is not None:
        body["now"] = "year"
        body["year"] = str(year)
    else:
        body["now"] = "month"

    payload = await post_fn(IBERICAM_RAIN_URL, body, _IBERICAM_TIMEOUT)
    return parse_ibericam_response(payload)


# ---------------------------------------------------------------------------
# Upsert en rainfall_records
# ---------------------------------------------------------------------------


async def upsert_ibericam_rainfall(
    db: AsyncSession,
    user_id: int,
    municipio_cod: str,
    records: list[tuple[datetime.date, float]],
    *,
    municipio_name: Optional[str] = None,
) -> dict[str, int]:
    """Crea o actualiza `RainfallRecord`s con source="ibericam".

    - Consulta los registros existentes para el usuario, municipio y fechas
      del lote de entrada.
    - Para cada (fecha, mm): si ya existe → actualiza precipitation_mm;
      si no → crea uno nuevo.
    - Llama a db.flush() al final; el commit queda en manos del caller.

    Devuelve {"created": N, "updated": N, "total": N}.
    """
    if not records:
        return {"created": 0, "updated": 0, "total": 0}

    dates = [d for d, _ in records]
    existing_result = await db.execute(
        select(RainfallRecord).where(
            and_(
                RainfallRecord.user_id == user_id,
                RainfallRecord.municipio_cod == municipio_cod,
                RainfallRecord.source == "ibericam",
                RainfallRecord.date.in_(dates),
            )
        )
    )
    existing_by_date: dict[datetime.date, RainfallRecord] = {
        r.date: r for r in existing_result.scalars().all()
    }

    created = 0
    updated = 0
    for date, mm in records:
        existing = existing_by_date.get(date)
        if existing is None:
            db.add(
                RainfallRecord(
                    user_id=user_id,
                    plot_id=None,
                    municipio_cod=municipio_cod,
                    municipio_name=municipio_name,
                    date=date,
                    precipitation_mm=mm,
                    source="ibericam",
                )
            )
            created += 1
        else:
            existing.precipitation_mm = mm
            if municipio_name and not existing.municipio_name:
                existing.municipio_name = municipio_name
            updated += 1

    await db.flush()
    return {"created": created, "updated": updated, "total": created + updated}


# ---------------------------------------------------------------------------
# Pipeline completo
# ---------------------------------------------------------------------------


async def import_ibericam_rainfall(
    db: AsyncSession,
    user_id: int,
    *,
    station_slug: str,
    municipio_cod: str,
    municipio_name: Optional[str] = None,
    year: Optional[int] = None,
    month: Optional[int] = None,
    http_post_json: Optional[HttpPostJson] = None,
) -> dict[str, int]:
    """Pipeline completo: fetch → parse → upsert en rainfall_records.

    Parámetros:
        db: sesión async activa.
        user_id: ID del usuario propietario de los registros.
        station_slug: slug de la estación ibericam (p. ej. "sarrion").
        municipio_cod: código INE del municipio (p. ej. "44216").
        year: año a importar (None = mes en curso / año en curso).
        month: mes a importar (1-12). Requiere year.
        http_post_json: función HTTP inyectable para tests.

    Devuelve dict con {"created", "updated", "total"}.
    """
    records = await get_daily_precipitation(
        station_slug,
        year=year,
        month=month,
        http_post_json=http_post_json,
    )
    # Resolver nombre del municipio si no viene del formulario
    resolved_name = (
        municipio_name
        or MUNICIPIO_COD_TO_NAME.get(municipio_cod)
        or _slug_to_display_name(station_slug)
    )
    return await upsert_ibericam_rainfall(
        db, user_id, municipio_cod, records, municipio_name=resolved_name
    )


# ---------------------------------------------------------------------------
# Descubrimiento de estaciones disponibles
# ---------------------------------------------------------------------------


def _slug_to_display_name(slug: str) -> str:
    """Convierte un slug tipo 'alcala-de-la-selva' en 'Alcala De La Selva'."""
    return slug.replace("-", " ").title()


# Mapping inverso: código INE → nombre de municipio.
# Generado automáticamente a partir de IBERICAM_SLUG_TO_MUNICIPIO.
MUNICIPIO_COD_TO_NAME: dict[str, str] = {
    cod: _slug_to_display_name(slug) for slug, cod in IBERICAM_SLUG_TO_MUNICIPIO.items()
}


async def scrape_ibericam_stations(
    *,
    http_get_text: Optional[HttpGetText] = None,
    http_post_json: Optional[HttpPostJson] = None,
    max_concurrent: int = 4,
) -> list[dict]:
    """Descubre las estaciones ibericam disponibles.

    Flujo:
    1. Descarga el sitemap XML de ibericam para obtener todos los slugs.
    2. Filtra slugs que corresponden a regiones, categorías o etiquetas temáticas.
    3. Sondea ``rainDaily.php`` en paralelo (semáforo ``max_concurrent``) para
       verificar qué slugs devuelven datos reales.
    4. Devuelve lista de dicts ``{slug, name, last_date, num_records}`` para las
       estaciones verificadas, ordenada por nombre.

    Args:
        http_get_text: función GET inyectable para tests.
        http_post_json: función POST inyectable para tests.
        max_concurrent: máximo de peticiones simultáneas al sondar la API.
    """
    get_fn = http_get_text or _default_get_text
    post_fn = http_post_json or _default_post_json

    # 1. Descargar sitemap XML
    xml_text = await get_fn(IBERICAM_SITEMAP_URL, _IBERICAM_TIMEOUT)

    # 2. Extraer slugs: URLs con patrón /lugar_webcam_el_tiempo/<slug>/
    slugs: list[str] = re.findall(
        r"/lugar_webcam_el_tiempo/([^/<]+)/",
        xml_text,
    )
    # Eliminar duplicados y slugs de categoría conocidos
    candidates = [
        s
        for s in dict.fromkeys(slugs)  # preservar orden, deduplicar
        if s not in _NON_STATION_SLUGS
    ]
    logger.info(
        "ibericam scraper: %d candidatos tras filtrar el sitemap",
        len(candidates),
    )

    # 3. Sondar la API en paralelo con semáforo
    semaphore = asyncio.Semaphore(max_concurrent)

    async def probe(slug: str) -> Optional[dict]:
        async with semaphore:
            try:
                body = {"station": slug, "now": "month"}
                payload = await post_fn(IBERICAM_RAIN_URL, body, 15.0)
                records = parse_ibericam_response(payload)
                if not records:
                    return None
                dates = [d for d, _ in records]
                return {
                    "slug": slug,
                    "name": _slug_to_display_name(slug),
                    "last_date": max(dates).isoformat(),
                    "num_records": len(records),
                }
            except Exception as exc:
                logger.debug("ibericam probe '%s': %s", slug, exc)
                return None

    results = await asyncio.gather(*[probe(s) for s in candidates])
    stations_by_slug: dict[str, dict] = {r["slug"]: r for r in results if r is not None}

    # Garantizar que los slugs conocidos siempre aparecen aunque el probe
    # devuelva vacío (p. ej. ibericam bloquea la IP del servidor en producción).
    for known_slug in IBERICAM_SLUG_TO_MUNICIPIO:
        if known_slug not in stations_by_slug:
            stations_by_slug[known_slug] = {
                "slug": known_slug,
                "name": _slug_to_display_name(known_slug),
                "last_date": None,
                "num_records": 0,
            }

    stations = sorted(stations_by_slug.values(), key=lambda x: x["name"])
    logger.info(
        "ibericam scraper: %d estaciones (%d verificadas, %d desde lista fija) de %d candidatos",
        len(stations),
        len([r for r in results if r is not None]),
        sum(1 for s in stations if s["num_records"] == 0),
        len(candidates),
    )
    return stations

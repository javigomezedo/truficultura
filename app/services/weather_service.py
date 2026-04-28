"""Servicio de tiempo meteorológico en tiempo real.

Fuentes de datos:
  1. AEMET OpenData (prioritaria):
       - observacion/convencional/dato/estacion/{idema} → temperatura, humedad
       - prediccion/especifica/municipio/diaria/{cod_ine} → previsión mañana
       - valores/climatologicos/diarios/datos/... → lluvia mensual acumulada y hoy
  2. Ibericam (fallback para lluvia si no hay estación AEMET en el municipio):
       - POST rainDaily.php → lluvia mensual acumulada

Flujo principal (get_weather_contexts):
  1. Obtener todos los municipio_cod únicos de las parcelas del usuario.
  2. Para cada municipio (en paralelo):
       a. Llamar al forecast AEMET (no requiere estación) para obtener nombre y previsión.
       b. Con el nombre del municipio, buscar la estación AEMET más cercana.
       c. Si hay estación: observación actual + climatología mensual AEMET.
       d. Si no hay estación: intentar lluvia mensual vía ibericam.
  3. Cachear el resultado 20 min por municipio_cod (caché en memoria por proceso).
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.plot import Plot
from app.services.aemet_service import AemetClient, find_aemet_station_for_municipio
from app.services.ibericam_service import (
    IBERICAM_SLUG_TO_MUNICIPIO,
    get_daily_precipitation,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Mappings estáticos
# ---------------------------------------------------------------------------

_GEO_JSON_PATH = Path(__file__).parent.parent / "static" / "js" / "municipios_geo.json"


def _build_ine_name_lookup() -> dict[str, str]:
    """Carga el JSON de municipios y construye un lookup cód_INE → nombre.

    El JSON almacena los nombres en mayúsculas (p.ej. "SARRION"); se aplica
    .title() para obtener "Sarrion". AEMET ya devuelve el nombre con tildes
    y casing correcto, por lo que este dict sólo se usa como fallback.
    """
    try:
        with _GEO_JSON_PATH.open(encoding="utf-8") as fh:
            data = json.load(fh)
        lookup: dict[str, str] = {}
        for prov_code, mun_list in data.get("municipalities", {}).items():
            for m in mun_list:
                ine = str(m.get("ine_code", "")).strip()
                if ine and ine != "0":
                    full_code = prov_code.zfill(2) + ine.zfill(3)
                    name = m.get("name", "")
                    if name:
                        lookup[full_code] = name.title()
        return lookup
    except Exception:
        logger.warning("No se pudo cargar el lookup de nombres de municipios")
        return {}


# Lookup estático cód_INE (5 dígitos) → nombre legible del municipio
_INE_CODE_TO_NAME: dict[str, str] = _build_ine_name_lookup()

# Inverso de IBERICAM_SLUG_TO_MUNICIPIO: municipio_cod → slug ibericam
_MUNICIPIO_TO_IBERICAM_SLUG: dict[str, str] = {
    cod: slug for slug, cod in IBERICAM_SLUG_TO_MUNICIPIO.items()
}

# ---------------------------------------------------------------------------
# Cachés en memoria (scope: proceso/worker)
# ---------------------------------------------------------------------------

# Caché de datos de tiempo: municipio_cod → {"data": dict, "fetched_at": datetime}
_weather_cache: dict[str, dict[str, Any]] = {}
_cache_lock = asyncio.Lock()
_CACHE_TTL_SECONDS = 20 * 60  # 20 minutos

# Caché de resolución estación: municipio_cod → indicativo AEMET o None
_station_cache: dict[str, Optional[str]] = {}
_station_cache_lock = asyncio.Lock()

# Caché del inventario completo de estaciones AEMET (descarga única por proceso)
_all_stations: Optional[list[dict]] = None
_all_stations_fetched_at: Optional[datetime.datetime] = None
_STATIONS_CACHE_TTL_SECONDS = 24 * 3600  # 24 horas
_all_stations_lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _parse_float(val: Any) -> Optional[float]:
    """Parsea un valor que puede ser float, int o string con coma europea."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    raw = str(val).strip()
    if not raw:
        return None
    try:
        return float(raw.replace(",", "."))
    except ValueError:
        return None


def _format_age_label(minutes: int) -> str:
    """Formatea 'hace X min' o 'hace Xh'."""
    if minutes < 60:
        return f"hace {minutes} min"
    hours = minutes // 60
    return f"hace {hours}h"


def _sum_monthly_rain(records: list[dict]) -> tuple[Optional[float], Optional[float]]:
    """Suma precipitación mensual acumulada y el total del día de hoy.

    Returns:
        (monthly_total_mm, today_mm)
    """
    today = datetime.date.today()
    total = 0.0
    today_val: Optional[float] = None

    for rec in records:
        date_str = str(rec.get("fecha", ""))
        try:
            rec_date = datetime.date.fromisoformat(date_str[:10])
        except ValueError:
            continue

        raw_prec = rec.get("prec")
        prec = _parse_float(raw_prec)
        if prec is None:
            # Valores traza AEMET (Ip, Acum, etc.) → 0.0
            prec = 0.0
        prec = max(prec, 0.0)
        total += prec
        if rec_date == today:
            today_val = prec

    return round(total, 1), today_val


# ---------------------------------------------------------------------------
# Helpers de base de datos
# ---------------------------------------------------------------------------


async def _get_user_municipios(
    db: AsyncSession,
    user_id: int,
) -> list[str]:
    """Devuelve la lista de códigos INE completos (5 dígitos) únicos del usuario.

    El formulario almacena el código LOCAL del municipio (ej. "210" para Sarrión)
    y el código de provincia por separado (ej. "44"). Esta función los combina para
    obtener el código INE completo que usa AEMET e ibericam (ej. "44210").
    Si el código ya tiene 5 dígitos (o no hay provincia_cod), se usa tal cual.
    """
    res = await db.execute(
        select(Plot.provincia_cod, Plot.municipio_cod)
        .where(Plot.user_id == user_id, Plot.municipio_cod.is_not(None))
        .order_by(Plot.id)
    )
    seen: set[str] = set()
    municipios: list[str] = []
    for prov_cod, mun_cod in res.all():
        if not mun_cod:
            continue
        # Construir código INE completo de 5 dígitos
        if prov_cod and len(mun_cod) < 5:
            full_cod = prov_cod.zfill(2) + mun_cod.zfill(3)
        else:
            full_cod = mun_cod
        if full_cod not in seen:
            seen.add(full_cod)
            municipios.append(full_cod)
    return municipios


# ---------------------------------------------------------------------------
# Descubrimiento de estación AEMET
# ---------------------------------------------------------------------------


async def _get_all_aemet_stations() -> list[dict]:
    """Descarga el inventario de estaciones AEMET con caché de 24 h."""
    global _all_stations, _all_stations_fetched_at

    async with _all_stations_lock:
        now = datetime.datetime.now(datetime.UTC)
        if (
            _all_stations is not None
            and _all_stations_fetched_at is not None
            and (now - _all_stations_fetched_at).total_seconds()
            < _STATIONS_CACHE_TTL_SECONDS
        ):
            return _all_stations

        try:
            client = AemetClient()
            stations = await client.fetch_dataset(
                "valores/climatologicos/inventarioestaciones/todasestaciones"
            )
            if isinstance(stations, list) and stations:
                _all_stations = stations
                _all_stations_fetched_at = now
                logger.info("AEMET stations cached: %d estaciones", len(stations))
                return _all_stations
        except Exception as exc:
            logger.warning("No se pudo descargar inventario AEMET: %s", exc)

        return _all_stations or []


async def _find_aemet_station(
    municipio_cod: str,
    municipio_name: str,
) -> Optional[str]:
    """Devuelve el indicativo AEMET para el municipio, cacheado por proceso."""
    async with _station_cache_lock:
        if municipio_cod in _station_cache:
            return _station_cache[municipio_cod]

    try:
        stations = await _get_all_aemet_stations()
        station_id = find_aemet_station_for_municipio(
            stations, municipio_cod, municipio_name
        )
    except Exception as exc:
        logger.warning(
            "Búsqueda de estación fallida (municipio=%s): %s", municipio_cod, exc
        )
        station_id = None

    async with _station_cache_lock:
        _station_cache[municipio_cod] = station_id
        logger.info(
            "Estación AEMET resuelta: municipio=%s → station=%s",
            municipio_cod,
            station_id,
        )
    return station_id


# ---------------------------------------------------------------------------
# Fetchers de AEMET
# ---------------------------------------------------------------------------


async def _fetch_current_observation(station_id: str) -> Optional[dict]:
    """Obtiene la última observación convencional de AEMET para una estación."""
    try:
        client = AemetClient()
        data = await client.fetch_dataset(
            f"observacion/convencional/dato/estacion/{station_id}"
        )
        if not isinstance(data, list) or not data:
            return None

        obs = data[-1]  # registro más reciente

        # Parsear timestamp
        fint_str = str(obs.get("fint", ""))
        updated_at: Optional[datetime.datetime] = None
        updated_ago_minutes: Optional[int] = None
        updated_ago_label: Optional[str] = None
        try:
            updated_at = datetime.datetime.fromisoformat(fint_str).replace(
                tzinfo=datetime.UTC
            )
            updated_ago_minutes = max(
                0,
                int(
                    (datetime.datetime.now(datetime.UTC) - updated_at).total_seconds()
                    / 60
                ),
            )
            updated_ago_label = _format_age_label(updated_ago_minutes)
        except (ValueError, TypeError):
            pass

        return {
            "temperature": _parse_float(obs.get("ta")),
            "humidity": _parse_float(obs.get("hr")),
            "precipitation_last": _parse_float(obs.get("prec")),
            "wind_speed": _parse_float(obs.get("vv")),
            "wind_dir_deg": _parse_float(obs.get("dv")),
            "updated_at": updated_at,
            "updated_ago_minutes": updated_ago_minutes,
            "updated_ago_label": updated_ago_label,
        }
    except Exception as exc:
        # 404 es normal para estaciones que no publican observación en tiempo real
        # (muy común en interiores). El fallback horario lo cubre — no es un error.
        if "404" in str(exc):
            logger.debug(
                "AEMET observation not available for station %s (404, using forecast fallback)",
                station_id,
            )
        else:
            logger.warning("AEMET observation error (station=%s): %s", station_id, exc)
        return None


async def _fetch_forecast(municipio_cod: str) -> Optional[dict]:
    """Obtiene la predicción diaria AEMET para un municipio (sin necesidad de estación).

    Devuelve datos del municipio y la previsión de mañana.
    """
    try:
        client = AemetClient()
        data = await client.fetch_dataset(
            f"prediccion/especifica/municipio/diaria/{municipio_cod}"
        )
        if not isinstance(data, list) or not data:
            return None

        entry = data[0]
        municipio_name: Optional[str] = entry.get("nombre")
        provincia_name: Optional[str] = entry.get("provincia")

        tomorrow = datetime.date.today() + datetime.timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        dias: list[dict] = entry.get("prediccion", {}).get("dia", [])
        tomorrow_dia = next(
            (d for d in dias if str(d.get("fecha", "")).startswith(tomorrow_str)),
            None,
        )

        tomorrow_sky: Optional[str] = None
        tomorrow_sky_code: Optional[str] = None
        tomorrow_t_max: Optional[int] = None
        tomorrow_t_min: Optional[int] = None
        tomorrow_prob_prec: Optional[int] = None

        if tomorrow_dia:
            cielos: list[dict] = tomorrow_dia.get("estadoCielo", [])
            # Preferir período completo (00-24); si no, el primero disponible
            cielo = next(
                (c for c in cielos if c.get("periodo") == "00-24"),
                cielos[0] if cielos else None,
            )
            if cielo:
                tomorrow_sky = cielo.get("descripcion") or None
                tomorrow_sky_code = str(cielo.get("value", "")) or None

            temp: dict = tomorrow_dia.get("temperatura", {})
            try:
                tomorrow_t_max = int(temp.get("maxima"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                tomorrow_t_max = None
            try:
                tomorrow_t_min = int(temp.get("minima"))  # type: ignore[arg-type]
            except (TypeError, ValueError):
                tomorrow_t_min = None

            prob_precs: list[dict] = tomorrow_dia.get("probPrecipitacion", [])
            prob_entry = next(
                (p for p in prob_precs if p.get("periodo") == "00-24"),
                prob_precs[0] if prob_precs else None,
            )
            if prob_entry:
                try:
                    tomorrow_prob_prec = int(prob_entry.get("value", 0))
                except (TypeError, ValueError):
                    tomorrow_prob_prec = None

        return {
            "municipio_name": municipio_name,
            "provincia_name": provincia_name,
            "tomorrow_sky": tomorrow_sky,
            "tomorrow_sky_code": tomorrow_sky_code,
            "tomorrow_t_max": tomorrow_t_max,
            "tomorrow_t_min": tomorrow_t_min,
            "tomorrow_prob_prec": tomorrow_prob_prec,
        }
    except Exception as exc:
        logger.warning("AEMET forecast error (municipio=%s): %s", municipio_cod, exc)
        return None


async def _fetch_aemet_monthly_rain(
    station_id: str,
) -> tuple[Optional[float], Optional[float]]:
    """Devuelve (total_mes_mm, hoy_mm) desde climatología diaria AEMET."""
    today = datetime.date.today()
    date_from = today.replace(day=1)
    fecha_ini = date_from.strftime("%Y-%m-%dT00:00:00UTC")
    fecha_fin = today.strftime("%Y-%m-%dT23:59:59UTC")
    try:
        client = AemetClient()
        data = await client.fetch_dataset(
            f"valores/climatologicos/diarios/datos/"
            f"fechaini/{fecha_ini}/fechafin/{fecha_fin}/estacion/{station_id}"
        )
        if isinstance(data, list):
            return _sum_monthly_rain(data)
    except Exception as exc:
        logger.warning("AEMET monthly rain error (station=%s): %s", station_id, exc)
    return None, None


# ---------------------------------------------------------------------------
# Fetcher ibericam
# ---------------------------------------------------------------------------


async def _fetch_ibericam_monthly_rain(slug: str) -> Optional[float]:
    """Suma de precipitación diaria del mes en curso vía ibericam."""
    today = datetime.date.today()
    try:
        records = await get_daily_precipitation(
            slug, year=today.year, month=today.month
        )
        total = sum(mm for _, mm in records if mm is not None)
        return round(total, 1)
    except Exception as exc:
        logger.warning("ibericam monthly rain error (slug=%s): %s", slug, exc)
    return None


# ---------------------------------------------------------------------------
# Fallback de temperatura/humedad desde predicción horaria
# ---------------------------------------------------------------------------


def _hour_es() -> int:
    """Hora local española aproximada (CEST=UTC+2 abr-oct, CET=UTC+1 nov-mar)."""
    now_utc = datetime.datetime.now(datetime.UTC)
    month = now_utc.month
    offset = 2 if 4 <= month <= 10 else 1
    return (now_utc.hour + offset) % 24


def _hourly_value(items: list[dict], hour: int) -> Optional[float]:
    """Devuelve el valor de la hora indicada (o el más próximo) de una lista AEMET.

    Los ítems tienen la forma ``{"value": "18", "periodo": "14"}``.
    """
    if not items:
        return None
    # Búsqueda exacta
    for item in items:
        if str(item.get("periodo", "")) == f"{hour:02d}":
            try:
                return float(str(item.get("value", "")).replace(",", "."))
            except (ValueError, TypeError):
                return None
    # Si no hay coincidencia exacta, usar el periodo más cercano
    best: Optional[float] = None
    best_diff = 999
    for item in items:
        try:
            p = int(str(item.get("periodo", "")))
            diff = min(abs(p - hour), 24 - abs(p - hour))  # circular
            if diff < best_diff:
                best_diff = diff
                raw = item.get("value")
                best = float(str(raw).replace(",", ".")) if raw else None
        except (ValueError, TypeError):
            continue
    return best


async def _fetch_hourly_forecast_obs(municipio_cod: str) -> Optional[dict]:
    """Temperatura y humedad de la predicción horaria AEMET para la hora actual.

    Se usa como fallback cuando el endpoint de observación convencional no está
    disponible (muy común en estaciones interiores). Devuelve un dict compatible
    con el de _fetch_current_observation pero sin timing de actualización y con
    is_forecast=True para distinguir el badge en el template.
    """
    try:
        client = AemetClient()
        data = await client.fetch_dataset(
            f"prediccion/especifica/municipio/horaria/{municipio_cod}"
        )
        if not isinstance(data, list) or not data:
            return None

        dias: list[dict] = data[0].get("prediccion", {}).get("dia", [])
        today_str = datetime.date.today().isoformat()
        today_dia = next(
            (d for d in dias if str(d.get("fecha", "")).startswith(today_str)),
            None,
        )
        if today_dia is None:
            return None

        hour = _hour_es()
        temperature = _hourly_value(today_dia.get("temperatura", []), hour)
        humidity = _hourly_value(today_dia.get("humedadRelativa", []), hour)

        if temperature is None:
            return None

        return {
            "temperature": temperature,
            "humidity": humidity,
            "precipitation_last": None,
            "wind_speed": None,
            "wind_dir_deg": None,
            "updated_at": None,
            "updated_ago_minutes": None,
            "updated_ago_label": None,
            "is_forecast": True,
        }
    except Exception as exc:
        logger.warning(
            "AEMET hourly forecast fallback error (municipio=%s): %s",
            municipio_cod,
            exc,
        )
    return None


# ---------------------------------------------------------------------------
# Constructor principal
# ---------------------------------------------------------------------------


async def _build_weather_data_for_municipio(municipio_cod: str) -> dict:
    """Construye datos de tiempo frescos para un único municipio. Sin caché aquí."""

    ibericam_slug = _MUNICIPIO_TO_IBERICAM_SLUG.get(municipio_cod)

    # Nombre preliminar desde el JSON estático (sync, disponible de inmediato).
    # Es suficiente para la búsqueda de estación mientras el forecast llega.
    preliminary_name: str = (
        _INE_CODE_TO_NAME.get(municipio_cod)
        or (ibericam_slug.replace("-", " ").title() if ibericam_slug else None)
        or municipio_cod
    )

    # Fase 1: forecast AEMET + warm-up del inventario de estaciones, en paralelo.
    # _get_all_aemet_stations() sólo descarga 1 vez (caché 24 h); aquí lo iniciamos
    # a la vez que el forecast para que _find_aemet_station() lo encuentre ya listo.
    forecast_result, _ = await asyncio.gather(
        _fetch_forecast(municipio_cod),
        _get_all_aemet_stations(),
        return_exceptions=True,
    )
    forecast: Optional[dict] = (
        None if isinstance(forecast_result, Exception) else forecast_result
    )

    # Nombre final: AEMET forecast (con tildes y casing correcto) > JSON estático
    municipio_name: str = (
        (forecast.get("municipio_name") if forecast else None)
        or preliminary_name
    )
    provincia_name: Optional[str] = forecast.get("provincia_name") if forecast else None
    display_name = (
        f"{municipio_name}, {provincia_name}"
        if municipio_name and provincia_name
        else (municipio_name or municipio_cod)
    )

    # Fase 2: resolver estación — el inventario ya está en caché, retorna al instante
    station_id = await _find_aemet_station(municipio_cod, municipio_name)

    # Fase 3: observación + lluvia mensual en paralelo (si hay estación)
    observation: Optional[dict] = None
    rain_month: Optional[float] = None
    rain_today: Optional[float] = None

    if station_id:
        observation, (rain_month, rain_today) = await asyncio.gather(
            _fetch_current_observation(station_id),
            _fetch_aemet_monthly_rain(station_id),
        )
        source = "aemet"
    else:
        source = "ibericam" if ibericam_slug else "none"

    # Fallback de temperatura/humedad desde predicción horaria cuando la estación
    # no publica observaciones en tiempo real (muy común en estaciones interiores).
    if observation is None:
        observation = await _fetch_hourly_forecast_obs(municipio_cod)
        if observation:
            # Ajustar source solo si no era ya 'aemet' (con estación pero sin obs)
            if source == "aemet":
                source = "aemet_forecast"

    # Fallback ibericam para lluvia mensual si AEMET no la tiene
    if rain_month is None and ibericam_slug:
        rain_month = await _fetch_ibericam_monthly_rain(ibericam_slug)
        if station_id and observation is not None:
            source = "aemet_partial"  # obs AEMET + lluvia ibericam

    # Badge de frescura
    updated_ago_minutes: Optional[int] = (
        observation.get("updated_ago_minutes") if observation else None
    )
    if observation and observation.get("is_forecast"):
        freshness = "info"  # datos de predicción horaria, no observación real
    elif updated_ago_minutes is not None:
        if updated_ago_minutes < 60:
            freshness = "success"
        elif updated_ago_minutes < 180:
            freshness = "warning"
        else:
            freshness = "danger"
    else:
        freshness = "secondary"

    # Precipitación "de hoy": primero climatología AEMET, fallback obs directa
    precipitation_today = rain_today
    if precipitation_today is None and observation:
        precipitation_today = observation.get("precipitation_last")

    return {
        "available": True,
        "source": source,
        "municipio_cod": municipio_cod,
        "municipio_name": municipio_name,
        "provincia_name": provincia_name,
        "display_name": display_name,
        "station_id": station_id,
        # Observación actual
        "temperature": observation.get("temperature") if observation else None,
        "humidity": observation.get("humidity") if observation else None,
        "precipitation_today": precipitation_today,
        "wind_speed": observation.get("wind_speed") if observation else None,
        "wind_dir_deg": observation.get("wind_dir_deg") if observation else None,
        # Lluvia mensual
        "rain_month": rain_month,
        # Timing
        "updated_ago_minutes": updated_ago_minutes,
        "updated_ago_label": (
            observation.get("updated_ago_label") if observation else None
        ),
        "freshness": freshness,
        # Previsión mañana
        "tomorrow_sky": forecast.get("tomorrow_sky") if forecast else None,
        "tomorrow_sky_code": forecast.get("tomorrow_sky_code") if forecast else None,
        "tomorrow_t_max": forecast.get("tomorrow_t_max") if forecast else None,
        "tomorrow_t_min": forecast.get("tomorrow_t_min") if forecast else None,
        "tomorrow_prob_prec": forecast.get("tomorrow_prob_prec") if forecast else None,
    }


async def _get_weather_for_municipio(municipio_cod: str) -> dict:
    """Wrapper de caché de 20 min por municipio_cod."""
    async with _cache_lock:
        cached = _weather_cache.get(municipio_cod)
        if cached:
            age = (
                datetime.datetime.now(datetime.UTC) - cached["fetched_at"]
            ).total_seconds()
            if age < _CACHE_TTL_SECONDS:
                return cached["data"]

    # Fuera del lock para no bloquear durante IO
    data = await _build_weather_data_for_municipio(municipio_cod)

    async with _cache_lock:
        _weather_cache[municipio_cod] = {
            "data": data,
            "fetched_at": datetime.datetime.now(datetime.UTC),
        }

    return data


async def get_weather_contexts(db: AsyncSession, user_id: int) -> list[dict]:
    """Devuelve una lista de contextos de tiempo, uno por municipio del usuario.

    Usa caché en memoria de 20 min por municipio_cod, compartida entre
    todos los usuarios del mismo municipio.
    """
    municipios = await _get_user_municipios(db, user_id)
    if not municipios:
        return [{"available": False, "error": "no_municipio"}]

    if not settings.AEMET_API_KEY:
        return [{"available": False, "error": "no_api_key"}]

    results = await asyncio.gather(
        *[_get_weather_for_municipio(cod) for cod in municipios]
    )
    return list(results)

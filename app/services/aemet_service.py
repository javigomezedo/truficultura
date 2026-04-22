from __future__ import annotations

import datetime
from typing import Any, Awaitable, Callable, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.rainfall import RainfallRecord


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _normalize_text(value: Any, *, max_len: int) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) > max_len:
        return text[:max_len]
    return text


HttpGetJson = Callable[
    [str, dict[str, str], float, Optional[dict[str, str]]], Awaitable[Any]
]

_UNSET = object()


class AemetClient:
    def __init__(
        self,
        *,
        api_key: Optional[str] | object = _UNSET,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        http_get_json: Optional[HttpGetJson] = None,
    ) -> None:
        self.api_key = settings.AEMET_API_KEY if api_key is _UNSET else api_key
        self.base_url = (base_url or settings.AEMET_BASE_URL).rstrip("/")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else settings.AEMET_TIMEOUT_SECONDS
        )
        self._http_get_json = http_get_json or self._default_http_get_json

    async def _default_http_get_json(
        self,
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
        params: Optional[dict[str, str]] = None,
    ) -> Any:
        import json as _json

        last_exc: Exception | None = None
        for _attempt in range(3):
            try:
                async with httpx.AsyncClient(
                    timeout=timeout_seconds, follow_redirects=True
                ) as client:
                    response = await client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    return _json.loads(response.content.decode("latin-1"))
            except httpx.RequestError as exc:
                last_exc = exc
        raise last_exc  # type: ignore[misc]

    async def fetch_dataset(
        self,
        endpoint_path: str,
        *,
        query_params: Optional[dict[str, str]] = None,
    ) -> Any:
        if not self.api_key:
            raise ValueError("AEMET_API_KEY no configurada")

        endpoint = endpoint_path.lstrip("/")
        url = f"{self.base_url}/{endpoint}"
        params: dict[str, str] = {"api_key": self.api_key}
        if query_params:
            params.update(query_params)

        headers = {"accept": "application/json"}
        metadata = await self._http_get_json(
            url,
            headers,
            self.timeout_seconds,
            params,
        )

        if isinstance(metadata, dict) and metadata.get("datos"):
            data_url = str(metadata["datos"])
            return await self._http_get_json(
                data_url,
                headers,
                self.timeout_seconds,
                None,
            )

        return metadata


def parse_precipitation_mm(value: Any) -> Optional[float]:
    if value is None:
        return 0.0

    if isinstance(value, (int, float)):
        return max(float(value), 0.0)

    raw = str(value).strip()
    if not raw:
        return 0.0

    if raw.lower() in {"ip", "tr", "trace"}:
        return 0.0

    normalized = raw.replace(",", ".")
    try:
        return max(float(normalized), 0.0)
    except ValueError:
        return None


def _parse_date(value: Any) -> Optional[datetime.date]:
    if value is None:
        return None

    if isinstance(value, datetime.date):
        return value

    raw = str(value).strip()
    if not raw:
        return None

    try:
        return datetime.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def normalize_daily_precip_records(
    payload: Any,
    *,
    is_forecast: bool,
    default_station_code: Optional[str] = None,
    default_province_code: Optional[str] = None,
    default_municipality_code: Optional[str] = None,
) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        date_value = _parse_date(item.get("fecha") or item.get("date"))
        precipitation_mm = parse_precipitation_mm(
            item.get("prec")
            or item.get("precipitacion")
            or item.get("precipitation_mm")
        )

        if date_value is None or precipitation_mm is None:
            continue

        station_code = (
            item.get("station_code") or item.get("indicativo") or default_station_code
        )
        province_code = (
            item.get("province_code")
            or item.get("provincia_cod")
            or default_province_code
        )
        municipality_code = (
            item.get("municipality_code")
            or item.get("municipio_cod")
            or default_municipality_code
        )

        normalized.append(
            {
                "date": date_value,
                "station_code": _normalize_text(station_code, max_len=20),
                "province_code": _normalize_text(province_code, max_len=10),
                "municipality_code": _normalize_text(municipality_code, max_len=10),
                "precipitation_mm": precipitation_mm,
                "is_forecast": is_forecast,
                "quality_status": "forecast" if is_forecast else "observed",
                "source": "aemet_api",
            }
        )

    return normalized


# ---------------------------------------------------------------------------
# Integración con rainfall_records
# ---------------------------------------------------------------------------


async def upsert_aemet_rainfall(
    db: AsyncSession,
    user_id: int,
    municipio_cod: str,
    records: list[dict[str, Any]],
    *,
    municipio_name: Optional[str] = None,
) -> dict[str, int]:
    """Crea o actualiza RainfallRecord con source='aemet' desde registros normalizados.

    Acepta la lista producida por ``normalize_daily_precip_records``.  Solo
    importa registros con ``is_forecast=False`` (observaciones reales).

    Devuelve {"created": N, "updated": N, "total": N}.
    """
    from sqlalchemy import and_

    observed = [r for r in records if not r.get("is_forecast", False)]
    if not observed:
        return {"created": 0, "updated": 0, "total": 0}

    dates = [r["date"] for r in observed]
    existing_result = await db.execute(
        select(RainfallRecord).where(
            and_(
                RainfallRecord.user_id == user_id,
                RainfallRecord.municipio_cod == municipio_cod,
                RainfallRecord.source == "aemet",
                RainfallRecord.date.in_(dates),
            )
        )
    )
    existing_by_date: dict[datetime.date, RainfallRecord] = {
        r.date: r for r in existing_result.scalars().all()
    }

    created = 0
    updated = 0
    for item in observed:
        date = item["date"]
        mm = item["precipitation_mm"]
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
                    source="aemet",
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


async def import_aemet_rainfall(
    db: AsyncSession,
    user_id: int,
    *,
    municipio_cod: str,
    municipio_name: Optional[str] = None,
    station_code: str,
    date_from: datetime.date,
    date_to: datetime.date,
    client: Optional[AemetClient] = None,
) -> dict[str, Any]:
    """Pipeline completo AEMET → rainfall_records.

    Consulta el endpoint de climatología diaria de AEMET para la estación y
    rango de fechas indicados, y persiste los datos observados en
    ``rainfall_records`` con ``source='aemet'``.

    Devuelve {"created", "updated", "total", "station_code", "municipio_cod"}.
    """
    fecha_ini = date_from.strftime("%Y-%m-%dT00:00:00UTC")
    fecha_fin = date_to.strftime("%Y-%m-%dT23:59:59UTC")
    endpoint = (
        f"/valores/climatologicos/diarios/datos/"
        f"fechaini/{fecha_ini}/fechafin/{fecha_fin}/estacion/{station_code}"
    )
    active_client = client or AemetClient()
    payload = await active_client.fetch_dataset(endpoint)
    normalized = normalize_daily_precip_records(
        payload,
        is_forecast=False,
        default_station_code=station_code,
    )
    result = await upsert_aemet_rainfall(
        db, user_id, municipio_cod, normalized, municipio_name=municipio_name
    )
    return {
        **result,
        "station_code": station_code,
        "municipio_cod": municipio_cod,
    }

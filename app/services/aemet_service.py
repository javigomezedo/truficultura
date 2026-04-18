from __future__ import annotations

import datetime
from typing import Any, Awaitable, Callable, Optional

import httpx

from app.config import settings


HttpGetJson = Callable[
    [str, dict[str, str], float, Optional[dict[str, str]]], Awaitable[Any]
]


class AemetClient:
    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        http_get_json: Optional[HttpGetJson] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.AEMET_API_KEY
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
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.get(url, headers=headers, params=params)
            response.raise_for_status()
            return response.json()

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
                "station_code": str(station_code) if station_code is not None else None,
                "province_code": str(province_code)
                if province_code is not None
                else None,
                "municipality_code": str(municipality_code)
                if municipality_code is not None
                else None,
                "precipitation_mm": precipitation_mm,
                "is_forecast": is_forecast,
                "quality_status": "forecast" if is_forecast else "observed",
                "source": "aemet_api",
            }
        )

    return normalized

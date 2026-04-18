from __future__ import annotations

import datetime

import pytest

from app.services.aemet_service import (
    AemetClient,
    normalize_daily_precip_records,
    parse_precipitation_mm,
)


def test_parse_precipitation_mm_handles_comma_value() -> None:
    assert parse_precipitation_mm("12,5") == pytest.approx(12.5)


def test_parse_precipitation_mm_handles_trace_values() -> None:
    assert parse_precipitation_mm("Ip") == 0.0


def test_parse_precipitation_mm_normalizes_negative_to_zero() -> None:
    assert parse_precipitation_mm(-1.4) == 0.0


def test_normalize_daily_precip_records_filters_invalid_rows() -> None:
    payload = [
        {"fecha": "2026-04-18", "prec": "3,2", "indicativo": "9999X"},
        {"fecha": "invalid", "prec": "2,0"},
        {"date": "2026-04-19", "precipitation_mm": "Ip"},
    ]

    rows = normalize_daily_precip_records(
        payload,
        is_forecast=False,
        default_province_code="44",
        default_municipality_code="223",
    )

    assert len(rows) == 2
    assert rows[0]["date"] == datetime.date(2026, 4, 18)
    assert rows[0]["precipitation_mm"] == pytest.approx(3.2)
    assert rows[0]["station_code"] == "9999X"
    assert rows[0]["is_forecast"] is False
    assert rows[1]["date"] == datetime.date(2026, 4, 19)
    assert rows[1]["precipitation_mm"] == 0.0


@pytest.mark.asyncio
async def test_fetch_dataset_uses_two_step_aemet_flow() -> None:
    calls: list[tuple[str, dict[str, str] | None]] = []

    async def fake_http_get_json(
        url: str,
        headers: dict[str, str],
        timeout_seconds: float,
        params: dict[str, str] | None,
    ):
        calls.append((url, params))
        if "opendata/api" in url:
            return {"estado": 200, "datos": "https://example.test/data.json"}
        return [{"fecha": "2026-04-18", "prec": "1,2"}]

    client = AemetClient(
        api_key="fake-key",
        http_get_json=fake_http_get_json,
    )

    payload = await client.fetch_dataset("/valores/climatologicos/diarios/datos")

    assert isinstance(payload, list)
    assert len(calls) == 2
    assert calls[0][0].endswith("/valores/climatologicos/diarios/datos")
    assert calls[0][1] is not None
    assert calls[0][1].get("api_key") == "fake-key"
    assert calls[1][0] == "https://example.test/data.json"


@pytest.mark.asyncio
async def test_fetch_dataset_requires_api_key() -> None:
    client = AemetClient(api_key=None)

    with pytest.raises(ValueError, match="AEMET_API_KEY"):
        await client.fetch_dataset("/valores/climatologicos/diarios/datos")

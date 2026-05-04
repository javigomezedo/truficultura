from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.aemet_service import (
    AemetClient,
    normalize_daily_precip_records,
    parse_precipitation_mm,
    upsert_aemet_rainfall,
)
from tests.conftest import result


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


def test_normalize_daily_precip_records_truncates_oversized_scope_values() -> None:
    payload = [
        {
            "fecha": "2026-04-18",
            "prec": "3,2",
            "indicativo": "1234567890123456789012345",
        }
    ]

    rows = normalize_daily_precip_records(
        payload,
        is_forecast=False,
        default_province_code="SANTA CRUZ DE TENERIFE",
        default_municipality_code="MUNICIPIO_CON_NOMBRE_MUY_LARGO",
    )

    assert len(rows) == 1
    assert rows[0]["station_code"] == "12345678901234567890"
    assert rows[0]["province_code"] == "SANTA CRUZ"
    assert rows[0]["municipality_code"] == "MUNICIPIO_"


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


# ---------------------------------------------------------------------------
# upsert_aemet_rainfall — integración con rainfall_records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_aemet_rainfall_creates_new_rainfall_records() -> None:
    from app.models.rainfall import RainfallRecord

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    records = [
        {
            "date": datetime.date(2026, 4, 1),
            "precipitation_mm": 3.2,
            "is_forecast": False,
        },
        {
            "date": datetime.date(2026, 4, 2),
            "precipitation_mm": 0.0,
            "is_forecast": False,
        },
    ]
    stats = await upsert_aemet_rainfall(db, municipio_cod="44210", records=records)

    assert stats == {"created": 2, "updated": 0, "total": 2}
    assert db.add.call_count == 2
    db.flush.assert_awaited_once()
    # Los registros creados son globales (user_id=None)
    added: RainfallRecord = db.add.call_args_list[0].args[0]
    assert added.tenant_id is None


@pytest.mark.asyncio
async def test_upsert_aemet_rainfall_updates_existing_record() -> None:
    existing = MagicMock()
    existing.date = datetime.date(2026, 4, 1)

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([existing]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    records = [
        {
            "date": datetime.date(2026, 4, 1),
            "precipitation_mm": 7.5,
            "is_forecast": False,
        }
    ]
    stats = await upsert_aemet_rainfall(db, municipio_cod="44210", records=records)

    assert stats == {"created": 0, "updated": 1, "total": 1}
    assert existing.precipitation_mm == pytest.approx(7.5)
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_upsert_aemet_rainfall_skips_forecasts() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    records = [
        {
            "date": datetime.date(2026, 4, 5),
            "precipitation_mm": 2.0,
            "is_forecast": True,
        },
        {
            "date": datetime.date(2026, 4, 6),
            "precipitation_mm": 1.5,
            "is_forecast": False,
        },
    ]
    stats = await upsert_aemet_rainfall(db, municipio_cod="44210", records=records)

    assert stats["total"] == 1
    assert stats["created"] == 1


@pytest.mark.asyncio
async def test_upsert_aemet_rainfall_empty_returns_zeros() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.flush = AsyncMock()

    stats = await upsert_aemet_rainfall(db, municipio_cod="44210", records=[])

    assert stats == {"created": 0, "updated": 0, "total": 0}
    db.flush.assert_not_awaited()

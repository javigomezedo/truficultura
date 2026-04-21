from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.water_balance_service import (
    get_plot_daily_water_balance,
    liters_per_second_to_m3_per_hour,
    precipitation_mm_to_m3,
)
from tests.conftest import result


def test_liters_per_second_to_m3_per_hour() -> None:
    assert liters_per_second_to_m3_per_hour(1.5) == pytest.approx(5.4)
    assert liters_per_second_to_m3_per_hour(None) is None


def test_precipitation_mm_to_m3() -> None:
    assert precipitation_mm_to_m3(10.0, 1.2) == pytest.approx(120.0)
    assert precipitation_mm_to_m3(None, 1.2) is None
    assert precipitation_mm_to_m3(10.0, None) is None


@pytest.mark.asyncio
async def test_get_plot_daily_water_balance_with_rainfall_record() -> None:
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="Parcela A",
        area_ha=1.5,
        water_flow_lps=2.0,
        provincia_cod="44",
        municipio_cod="44223",
    )
    irrigation = SimpleNamespace(water_m3=12.0)
    rainfall_record = SimpleNamespace(precipitation_mm=3.5)

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([irrigation]),
            result([rainfall_record]),  # hit en plot_id
        ]
    )

    balance = await get_plot_daily_water_balance(
        db,
        user_id=1,
        plot_id=1,
        target_date=datetime.date(2026, 4, 18),
    )

    assert balance is not None
    assert balance["rainfall_source"] == "plot"
    assert balance["precipitation_mm"] == pytest.approx(3.5)
    assert balance["rain_m3"] == pytest.approx(52.5)
    assert balance["irrigation_m3"] == pytest.approx(12.0)
    assert balance["total_water_m3"] == pytest.approx(64.5)
    assert balance["water_flow_m3_per_hour"] == pytest.approx(7.2)


@pytest.mark.asyncio
async def test_get_plot_daily_water_balance_no_rainfall_returns_none_precipitation() -> (
    None
):
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="Parcela A",
        area_ha=1.0,
        water_flow_lps=None,
        provincia_cod="44",
        municipio_cod="44223",
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([]),  # sin riego
            result([]),  # sin registro plot_id
            result([]),  # sin registro municipio
        ]
    )

    balance = await get_plot_daily_water_balance(
        db,
        user_id=1,
        plot_id=1,
        target_date=datetime.date(2026, 4, 18),
    )

    assert balance is not None
    assert balance["rainfall_source"] == "none"
    assert balance["precipitation_mm"] is None
    assert balance["rain_m3"] is None
    assert balance["irrigation_events_count"] == 0


@pytest.mark.asyncio
async def test_get_plot_daily_water_balance_returns_none_when_plot_missing() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    balance = await get_plot_daily_water_balance(
        db,
        user_id=1,
        plot_id=999,
        target_date=datetime.date(2026, 4, 18),
    )

    assert balance is None

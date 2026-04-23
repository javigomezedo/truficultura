from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.rainfall_service import select_best_rainfall_per_day
from app.services.water_balance_service import (
    get_plot_daily_water_balance,
    precipitation_mm_to_m3,
    simulate_irrigation,
)
from tests.conftest import result


def test_precipitation_mm_to_m3() -> None:
    assert precipitation_mm_to_m3(10.0, 1.2) == pytest.approx(120.0)
    assert precipitation_mm_to_m3(None, 1.2) is None
    assert precipitation_mm_to_m3(10.0, None) is None


# ---------------------------------------------------------------------------
# Tests de select_best_rainfall_per_day
# ---------------------------------------------------------------------------


def _rain(plot_id, source, date, mm, municipio_cod=None):
    return SimpleNamespace(
        plot_id=plot_id,
        source=source,
        date=date,
        precipitation_mm=mm,
        municipio_cod=municipio_cod,
    )


DATE = datetime.date(2026, 4, 18)
MUN = "44223"


def test_select_best_prefers_manual_over_aemet() -> None:
    manual = _rain(1, "manual", DATE, 5.0)
    aemet = _rain(None, "aemet", DATE, 10.0, MUN)
    best = select_best_rainfall_per_day([manual, aemet], plot_id=1, municipio_cod=MUN)
    assert best[DATE] == (5.0, "manual")


def test_select_best_prefers_aemet_over_ibericam() -> None:
    aemet = _rain(None, "aemet", DATE, 8.0, MUN)
    ibericam = _rain(None, "ibericam", DATE, 12.0, MUN)
    best = select_best_rainfall_per_day([aemet, ibericam], plot_id=1, municipio_cod=MUN)
    assert best[DATE] == (8.0, "aemet")


def test_select_best_falls_back_to_ibericam() -> None:
    ibericam = _rain(None, "ibericam", DATE, 3.0, MUN)
    best = select_best_rainfall_per_day([ibericam], plot_id=1, municipio_cod=MUN)
    assert best[DATE] == (3.0, "ibericam")


def test_select_best_empty_records() -> None:
    best = select_best_rainfall_per_day([], plot_id=1, municipio_cod=MUN)
    assert best == {}


def test_select_best_ignores_unrelated_municipio() -> None:
    other_mun = _rain(None, "aemet", DATE, 99.0, "99999")
    best = select_best_rainfall_per_day([other_mun], plot_id=1, municipio_cod=MUN)
    assert best == {}


# ---------------------------------------------------------------------------
# Tests de get_plot_daily_water_balance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_plot_daily_water_balance_with_rainfall_record() -> None:
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="Parcela A",
        area_ha=1.5,
        caudal_riego=7.2,
        provincia_cod="44",
        municipio_cod="44223",
    )
    irrigation = SimpleNamespace(water_m3=12.0)
    # registro manual directo a la parcela
    rainfall_record = SimpleNamespace(
        plot_id=1,
        source="manual",
        date=datetime.date(2026, 4, 18),
        precipitation_mm=3.5,
        municipio_cod=None,
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([irrigation]),
            result([rainfall_record]),  # combined rainfall query
        ]
    )

    balance = await get_plot_daily_water_balance(
        db,
        user_id=1,
        plot_id=1,
        target_date=datetime.date(2026, 4, 18),
    )

    assert balance is not None
    assert balance["rainfall_source"] == "manual"
    assert balance["precipitation_mm"] == pytest.approx(3.5)
    assert balance["rain_m3"] == pytest.approx(52.5)
    assert balance["irrigation_m3"] == pytest.approx(12.0)
    assert balance["total_water_m3"] == pytest.approx(64.5)
    assert balance["caudal_riego"] == pytest.approx(7.2)


@pytest.mark.asyncio
async def test_get_plot_daily_water_balance_aemet_preferred_over_ibericam() -> None:
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="P",
        area_ha=1.0,
        caudal_riego=None,
        provincia_cod="44",
        municipio_cod="44223",
    )
    aemet_rec = SimpleNamespace(
        plot_id=None,
        source="aemet",
        date=datetime.date(2026, 4, 18),
        precipitation_mm=7.0,
        municipio_cod="44223",
    )
    ibericam_rec = SimpleNamespace(
        plot_id=None,
        source="ibericam",
        date=datetime.date(2026, 4, 18),
        precipitation_mm=15.0,
        municipio_cod="44223",
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([]),
            result([aemet_rec, ibericam_rec]),
        ]
    )

    balance = await get_plot_daily_water_balance(
        db,
        user_id=1,
        plot_id=1,
        target_date=datetime.date(2026, 4, 18),
    )

    assert balance["rainfall_source"] == "aemet"
    assert balance["precipitation_mm"] == pytest.approx(7.0)


@pytest.mark.asyncio
async def test_get_plot_daily_water_balance_no_rainfall_returns_none_precipitation() -> (
    None
):
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="Parcela A",
        area_ha=1.0,
        caudal_riego=None,
        provincia_cod="44",
        municipio_cod="44223",
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([]),  # sin riego
            result([]),  # sin lluvia (combined query)
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


# ---------------------------------------------------------------------------
# Tests de simulate_irrigation
# ---------------------------------------------------------------------------


def _make_thresholds(status, plateau, sample_size=5):
    return {
        "status": status,
        "plateau_start_m3": plateau,
        "sample_size": sample_size,
        "marginal_gains": [],
    }


@pytest.mark.asyncio
async def test_simulate_irrigation_plot_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    sim = await simulate_irrigation(
        db, user_id=1, plot_id=99, sim_date=datetime.date(2026, 6, 1)
    )
    assert sim is None


@pytest.mark.asyncio
async def test_simulate_irrigation_insufficient_data() -> None:
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="P",
        area_ha=1.0,
        caudal_riego=2.0,
        provincia_cod=None,
        municipio_cod=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),  # plot query
            result([]),  # irrigation records
            result([]),  # rainfall records
            # detect_irrigation_thresholds por parcela → get_campaign_dataset:
            result([plot]),  # plots
            result([]),  # incomes
            result([]),  # irrigation
            result([]),  # wells
            result([]),  # events
            result([]),  # rainfall
            # fallback global → get_campaign_dataset de nuevo:
            result([plot]),  # plots
            result([]),  # incomes
            result([]),  # irrigation
            result([]),  # wells
            result([]),  # events
            result([]),  # rainfall
        ]
    )

    sim = await simulate_irrigation(
        db, user_id=1, plot_id=1, sim_date=datetime.date(2026, 6, 1)
    )

    assert sim is not None
    assert sim["should_irrigate"] is None
    assert sim["reason"] == "insufficient_data"
    assert sim["threshold_scope"] is None


@pytest.mark.asyncio
async def test_simulate_irrigation_plateau_reached() -> None:
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="P",
        area_ha=None,
        caudal_riego=None,
        provincia_cod=None,
        municipio_cod=None,
    )
    db = MagicMock()

    with patch(
        "app.services.plot_analytics_service.detect_irrigation_thresholds",
        new=AsyncMock(return_value=_make_thresholds("ok", 50.0)),
    ):
        db.execute = AsyncMock(
            side_effect=[
                result([plot]),  # plot
                result(
                    [SimpleNamespace(water_m3=30.0), SimpleNamespace(water_m3=25.0)]
                ),  # irrigation → 55 m³
                result([]),  # rainfall
            ]
        )

        sim = await simulate_irrigation(
            db, user_id=1, plot_id=1, sim_date=datetime.date(2026, 6, 1)
        )

    assert sim["should_irrigate"] is False
    assert sim["reason"] == "plateau_reached"
    assert sim["total_water_m3"] == pytest.approx(55.0)


@pytest.mark.asyncio
async def test_simulate_irrigation_should_irrigate_with_flow() -> None:
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="P",
        area_ha=None,
        caudal_riego=14.4,
        provincia_cod=None,
        municipio_cod=None,
    )
    db = MagicMock()

    with patch(
        "app.services.plot_analytics_service.detect_irrigation_thresholds",
        new=AsyncMock(return_value=_make_thresholds("ok", 100.0)),
    ):
        db.execute = AsyncMock(
            side_effect=[
                result([plot]),
                result([SimpleNamespace(water_m3=20.0)]),  # 20 m³ riego
                result([]),  # sin lluvia
            ]
        )

        sim = await simulate_irrigation(
            db, user_id=1, plot_id=1, sim_date=datetime.date(2026, 6, 1)
        )

    assert sim["should_irrigate"] is True
    assert sim["reason"] == "below_plateau"
    assert sim["remaining_m3"] == pytest.approx(80.0)
    # hours = 80 / 14.4 m³/h ≈ 5.56
    assert sim["hours_needed"] == pytest.approx(5.56, rel=1e-2)


@pytest.mark.asyncio
async def test_simulate_irrigation_should_irrigate_no_flow() -> None:
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="P",
        area_ha=None,
        caudal_riego=None,
        provincia_cod=None,
        municipio_cod=None,
    )
    db = MagicMock()

    with patch(
        "app.services.plot_analytics_service.detect_irrigation_thresholds",
        new=AsyncMock(return_value=_make_thresholds("ok", 100.0)),
    ):
        db.execute = AsyncMock(
            side_effect=[
                result([plot]),
                result([]),
                result([]),
            ]
        )

        sim = await simulate_irrigation(
            db, user_id=1, plot_id=1, sim_date=datetime.date(2026, 6, 1)
        )

    assert sim["should_irrigate"] is True
    assert sim["hours_needed"] is None


@pytest.mark.asyncio
async def test_simulate_irrigation_includes_rainfall_in_total() -> None:
    """La lluvia acumulada de campaña debe sumarse al riego en total_water_m3."""
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="P",
        area_ha=2.0,
        caudal_riego=None,
        provincia_cod="44",
        municipio_cod="44223",
    )
    rain_record = SimpleNamespace(
        plot_id=None,
        source="aemet",
        date=datetime.date(2026, 6, 5),
        precipitation_mm=10.0,
        municipio_cod="44223",
    )
    db = MagicMock()

    with patch(
        "app.services.plot_analytics_service.detect_irrigation_thresholds",
        new=AsyncMock(return_value=_make_thresholds("ok", 500.0)),
    ):
        db.execute = AsyncMock(
            side_effect=[
                result([plot]),
                result([SimpleNamespace(water_m3=5.0)]),  # 5 m³ riego
                result([rain_record]),  # 10 mm × 2 ha × 10 = 200 m³ lluvia
            ]
        )

        sim = await simulate_irrigation(
            db, user_id=1, plot_id=1, sim_date=datetime.date(2026, 6, 10)
        )

    assert sim["rain_mm"] == pytest.approx(10.0)
    assert sim["rain_m3"] == pytest.approx(200.0)
    assert sim["total_water_m3"] == pytest.approx(205.0)


@pytest.mark.asyncio
async def test_simulate_irrigation_uses_plot_threshold_when_sufficient_data() -> None:
    """Con ≥5 campañas propias se usa el umbral de la parcela (threshold_scope='plot')."""
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="P",
        area_ha=None,
        caudal_riego=None,
        provincia_cod=None,
        municipio_cod=None,
    )
    db = MagicMock()

    with patch(
        "app.services.plot_analytics_service.detect_irrigation_thresholds",
        new=AsyncMock(return_value=_make_thresholds("ok", 100.0, sample_size=6)),
    ):
        db.execute = AsyncMock(
            side_effect=[
                result([plot]),
                result([]),
                result([]),
            ]
        )

        sim = await simulate_irrigation(
            db, user_id=1, plot_id=1, sim_date=datetime.date(2026, 6, 1)
        )

    assert sim is not None
    assert sim["threshold_scope"] == "plot"
    assert sim["should_irrigate"] is True  # total=0 < plateau=100


@pytest.mark.asyncio
async def test_simulate_irrigation_falls_back_to_global_threshold() -> None:
    """Con <5 campañas propias pero datos globales suficientes, usa umbral global."""
    plot = SimpleNamespace(
        id=1,
        user_id=1,
        name="P",
        area_ha=None,
        caudal_riego=None,
        provincia_cod=None,
        municipio_cod=None,
    )
    db = MagicMock()

    with patch(
        "app.services.plot_analytics_service.detect_irrigation_thresholds",
        new=AsyncMock(
            side_effect=[
                _make_thresholds("ok", 80.0, sample_size=3),  # por parcela: ok pero <5
                _make_thresholds("ok", 120.0, sample_size=10),  # global: suficiente
            ]
        ),
    ):
        db.execute = AsyncMock(
            side_effect=[
                result([plot]),
                result([]),
                result([]),
            ]
        )

        sim = await simulate_irrigation(
            db, user_id=1, plot_id=1, sim_date=datetime.date(2026, 6, 1)
        )

    assert sim is not None
    assert sim["threshold_scope"] == "global"
    assert sim["plateau_start_m3"] == pytest.approx(120.0)  # usa meseta global
    assert sim["sample_size"] == 10

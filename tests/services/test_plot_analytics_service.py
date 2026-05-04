from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.plot_analytics_service import (
    detect_irrigation_thresholds,
    get_all_plot_thresholds,
    get_campaign_dataset,
    get_irrigation_vs_production_analysis,
    get_multi_plot_comparison,
    get_plot_detail_context,
    get_pruning_vs_production_analysis,
    get_tilling_vs_production_analysis,
)
from tests.conftest import result


@pytest.mark.asyncio
async def test_get_campaign_dataset_aggregates_metrics() -> None:
    plot = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    income = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=50.0
    )
    irrigation = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=10.0
    )
    well = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 3), wells_per_plant=2
    )
    event_poda = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 4), event_type="poda"
    )
    event_labrado = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 5), event_type="labrado"
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([income]),
            result([irrigation]),
            result([well]),
            result([event_poda, event_labrado]),
            result([]),  # rainfall query
        ]
    )

    rows = await get_campaign_dataset(db, tenant_id=1)

    assert len(rows) == 1
    row = rows[0]
    assert row["campaign_year"] == 2025
    assert row["total_production_kg"] == 50.0
    assert row["total_water_m3"] == 10.0
    assert row["pruning_events_count"] == 1
    assert row["tilling_events_count"] == 1
    assert row["well_events_count"] == 1
    assert row["wells_per_plant_total"] == 2


@pytest.mark.asyncio
async def test_get_campaign_dataset_filters_campaign_range() -> None:
    plot = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    income_2025 = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=50.0
    )
    income_2024 = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 1), amount_kg=30.0
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([income_2025, income_2024]),
            result([]),
            result([]),
            result([]),
            result([]),  # rainfall query
        ]
    )

    rows = await get_campaign_dataset(db, tenant_id=1, campaign_from=2025)

    assert len(rows) == 1
    assert rows[0]["campaign_year"] == 2025


@pytest.mark.asyncio
async def test_get_irrigation_vs_production_analysis() -> None:
    db = MagicMock()

    # Reuse get_campaign_dataset via mocked DB calls (plots, incomes, irrigation, wells, events)
    plot = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    incomes = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=50.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=60.0
        ),
    ]
    irrigation = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 2), water_m3=20.0
        ),
    ]

    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result(incomes),
            result(irrigation),
            result([]),
            result([]),
            result([]),  # rainfall query
        ]
    )

    analysis = await get_irrigation_vs_production_analysis(db, tenant_id=1)

    assert analysis["sample_size"] == 2
    assert analysis["avg_water_m3"] > 0
    assert analysis["avg_production_kg"] > 0
    assert len(analysis["water_bands"]) == 3
    for band in analysis["water_bands"]:
        assert "min_m3" in band
        assert "max_m3" in band
    bajo = next(b for b in analysis["water_bands"] if b["band"] == "bajo")
    assert bajo["min_m3"] == 0.0
    assert bajo["max_m3"] is not None
    alto = next(b for b in analysis["water_bands"] if b["band"] == "alto")
    assert alto["max_m3"] is None


@pytest.mark.asyncio
async def test_get_pruning_vs_production_analysis() -> None:
    plot = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    income_a = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=80.0
    )
    income_b = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=40.0
    )
    event_pruning = SimpleNamespace(
        tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), event_type="poda"
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([income_a, income_b]),
            result([]),
            result([]),
            result([event_pruning]),
            result([]),  # rainfall query
        ]
    )

    analysis = await get_pruning_vs_production_analysis(db, tenant_id=1)

    assert analysis["sample_size"] == 2
    assert analysis["with_pruning_count"] == 1
    assert analysis["without_pruning_count"] == 1
    assert analysis["delta_percent"] == 100.0


@pytest.mark.asyncio
async def test_get_tilling_vs_production_analysis() -> None:
    plot = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    incomes = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=20.0
        ),
    ]
    events = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 2), event_type="labrado"
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result(incomes),
            result([]),
            result([]),
            result(events),
            result([]),  # rainfall query
        ]
    )

    analysis = await get_tilling_vs_production_analysis(db, tenant_id=1)

    assert analysis["sample_size"] == 2
    assert len(analysis["groups"]) == 2
    assert sum(item["count"] for item in analysis["groups"]) == 2
    con_labrado = next(g for g in analysis["groups"] if g["group"] == "con_labrado")
    sin_labrado = next(g for g in analysis["groups"] if g["group"] == "sin_labrado")
    assert con_labrado["count"] == 1
    assert sin_labrado["count"] == 1


@pytest.mark.asyncio
async def test_detect_irrigation_thresholds() -> None:
    plot = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    incomes = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=20.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=21.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2027, 6, 1), amount_kg=21.1
        ),
    ]
    irrigation = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 2), water_m3=20.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2027, 6, 2), water_m3=30.0
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result(incomes),
            result(irrigation),
            result([]),
            result([]),
            result([]),  # rainfall query
        ]
    )

    analysis = await detect_irrigation_thresholds(db, tenant_id=1)

    assert analysis["sample_size"] == 3
    assert analysis["status"] == "ok"
    assert len(analysis["marginal_gains"]) == 2


@pytest.mark.asyncio
async def test_detect_irrigation_thresholds_inconclusive_first_transition() -> None:
    """Si el primer par ya dispara la meseta, el status es 'inconclusive'."""
    plot = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    # Sorted by water: (10, 200), (30, 100), (50, 250)
    # Transition 0: 10→30: Δprod=-100, gain=-5.0 ≤ 0.02 → plateau at 30 (i=0) → inconclusive
    incomes = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2023, 6, 1), amount_kg=200.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 1), amount_kg=100.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=250.0
        ),
    ]
    irrigation = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2023, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 2), water_m3=30.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=50.0
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result(incomes),
            result(irrigation),
            result([]),
            result([]),
            result([]),  # rainfall query
        ]
    )

    analysis = await detect_irrigation_thresholds(db, tenant_id=1)

    assert analysis["status"] == "inconclusive"
    assert analysis["plateau_start_m3"] is None


@pytest.mark.asyncio
async def test_detect_irrigation_thresholds_inconclusive_noisy() -> None:
    """Si más del 60 % de las ganancias son negativas, el status es 'inconclusive'."""
    plot = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    # Sorted by water: (10,100), (20,150), (30,120), (40,90), (50,70)
    # Transition 0: 10→20: gain=+5.0 (positive, not plateau)
    # Transition 1: 20→30: gain=-3.0 (negative, plateau at 30, i=1 → not first)
    # Transition 2: 30→40: gain=-3.0 (negative)
    # Transition 3: 40→50: gain=-2.0 (negative)
    # negative_count=3, total=4, ratio=0.75 > 0.60 → noisy → inconclusive
    incomes = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2021, 6, 1), amount_kg=100.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2022, 6, 1), amount_kg=150.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2023, 6, 1), amount_kg=120.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 1), amount_kg=90.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=70.0
        ),
    ]
    irrigation = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2021, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2022, 6, 2), water_m3=20.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2023, 6, 2), water_m3=30.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 2), water_m3=40.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=50.0
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result(incomes),
            result(irrigation),
            result([]),
            result([]),
            result([]),  # rainfall query
        ]
    )

    analysis = await detect_irrigation_thresholds(db, tenant_id=1)

    assert analysis["status"] == "inconclusive"
    assert analysis["plateau_start_m3"] is None
    assert len(analysis["marginal_gains"]) == 4


@pytest.mark.asyncio
async def test_detect_irrigation_thresholds_median_of_plots() -> None:
    """Con ≥2 parcelas con umbral fiable, devuelve la mediana de sus mesetas."""
    plot1 = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    plot2 = SimpleNamespace(
        id=2,
        tenant_id=1,
        name="Parcela B",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    # Plot 1: water 10→20→30, prod 5→10→10.1 → plateau at 30 m³
    # Plot 2: water 15→25→35, prod 8→15→15.1 → plateau at 35 m³
    # Median of [30, 35] = 32.5
    incomes = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 1), amount_kg=5.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=10.1
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2024, 6, 1), amount_kg=8.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2025, 6, 1), amount_kg=15.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2026, 6, 1), amount_kg=15.1
        ),
    ]
    irrigation = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=20.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2026, 6, 2), water_m3=30.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2024, 6, 2), water_m3=15.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2025, 6, 2), water_m3=25.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2026, 6, 2), water_m3=35.0
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot1, plot2]),
            result(incomes),
            result(irrigation),
            result([]),  # wells
            result([]),  # events
            result([]),  # rainfall
        ]
    )

    analysis = await detect_irrigation_thresholds(db, tenant_id=1)

    assert analysis["method"] == "median_of_plots"
    assert analysis["contributing_plots"] == 2
    assert analysis["status"] == "ok"
    assert analysis["plateau_start_m3"] == 32.5
    assert analysis["sample_size"] == 6


@pytest.mark.asyncio
async def test_get_plot_detail_context_found() -> None:
    plot = SimpleNamespace(
        id=10,
        tenant_id=1,
        name="Parcela Z",
        num_plants=100,
        has_irrigation=True,
        sector="A",
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    income = SimpleNamespace(
        tenant_id=1, plot_id=10, date=datetime.date(2025, 6, 1), amount_kg=42.0
    )
    irrigation = SimpleNamespace(
        tenant_id=1, plot_id=10, date=datetime.date(2025, 6, 2), water_m3=11.0
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([plot]),
            result([income]),
            result([irrigation]),
            result([]),
            result([]),
            result([]),  # rainfall query
        ]
    )

    context = await get_plot_detail_context(db, tenant_id=1, plot_id=10)

    assert context is not None
    assert context["plot"].name == "Parcela Z"
    assert context["labels"] == [2025]
    assert context["production_series"] == [42.0]
    assert context["water_series"] == [11.0]
    assert len(context["scatter_points"]) == 1
    assert context["insights"]["status"] == "ok"
    assert context["insights"]["best_campaign_year"] == 2025
    assert context["insights"]["best_campaign_production_kg"] == 42.0


@pytest.mark.asyncio
async def test_get_plot_detail_context_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    context = await get_plot_detail_context(db, tenant_id=1, plot_id=999)

    assert context is None


@pytest.mark.asyncio
async def test_get_multi_plot_comparison() -> None:
    plot_a = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    plot_b = SimpleNamespace(
        id=2,
        tenant_id=1,
        name="Parcela B",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    incomes = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=40.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2025, 6, 1), amount_kg=30.0
        ),
    ]
    irrigation = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2025, 6, 2), water_m3=20.0
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot_a, plot_b]),
            result(incomes),
            result(irrigation),
            result([]),
            result([]),
            result([]),  # rainfall query
        ]
    )

    comparison = await get_multi_plot_comparison(db, tenant_id=1)

    assert comparison["sample_size"] == 2
    assert comparison["plots_included"] == 2
    assert len(comparison["points"]) == 2
    assert comparison["efficiency_ranking"][0]["plot_name"] == "Parcela A"


@pytest.mark.asyncio
async def test_get_all_plot_thresholds_per_plot() -> None:
    """Dos parcelas con datos suficientes → se calcula umbral para cada una."""
    plot_a = SimpleNamespace(
        id=1,
        tenant_id=1,
        name="Parcela A",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    plot_b = SimpleNamespace(
        id=2,
        tenant_id=1,
        name="Parcela B",
        num_plants=100,
        has_irrigation=True,
        area_ha=None,
        municipio_cod=None,
        provincia_cod=None,
    )
    # Parcela A: 3 campañas con agua y producción (suficientes)
    incomes = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2023, 6, 1), amount_kg=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 1), amount_kg=10.5
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=10.6
        ),
        # Parcela B: sólo 1 campaña
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2025, 6, 1), amount_kg=20.0
        ),
    ]
    irrigation = [
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2023, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2024, 6, 2), water_m3=20.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=30.0
        ),
        SimpleNamespace(
            tenant_id=1, plot_id=2, date=datetime.date(2025, 6, 2), water_m3=15.0
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot_a, plot_b]),
            result(incomes),
            result(irrigation),
            result([]),
            result([]),
            result([]),  # rainfall query
        ]
    )

    thresholds = await get_all_plot_thresholds(db, tenant_id=1)

    assert len(thresholds) == 2
    by_name = {t["plot_name"]: t for t in thresholds}

    assert by_name["Parcela A"]["status"] == "ok"
    assert by_name["Parcela A"]["sample_size"] == 3

    assert by_name["Parcela B"]["status"] == "insufficient_data"
    assert by_name["Parcela B"]["sample_size"] == 1
    assert by_name["Parcela B"]["plateau_start_m3"] is None

    # El resultado debe estar ordenado alfabéticamente
    assert thresholds[0]["plot_name"] == "Parcela A"

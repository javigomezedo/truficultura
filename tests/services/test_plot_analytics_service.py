from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.plot_analytics_service import (
    detect_irrigation_thresholds,
    get_campaign_dataset,
    get_irrigation_vs_production_analysis,
    get_multi_plot_comparison,
    get_plot_detail_context,
    get_pruning_vs_production_analysis,
    get_tilling_digging_vs_production_analysis,
)
from tests.conftest import result


@pytest.mark.asyncio
async def test_get_campaign_dataset_aggregates_metrics() -> None:
    plot = SimpleNamespace(
        id=1, user_id=1, name="Parcela A", num_plants=100, has_irrigation=True
    )
    income = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=50.0
    )
    irrigation = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=10.0
    )
    well = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2025, 6, 3), wells_per_plant=2
    )
    event_poda = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2025, 6, 4), event_type="poda"
    )
    event_labrado = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2025, 6, 5), event_type="labrado"
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([income]),
            result([irrigation]),
            result([well]),
            result([event_poda, event_labrado]),
        ]
    )

    rows = await get_campaign_dataset(db, user_id=1)

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
        id=1, user_id=1, name="Parcela A", num_plants=100, has_irrigation=True
    )
    income_2025 = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=50.0
    )
    income_2024 = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2024, 6, 1), amount_kg=30.0
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([income_2025, income_2024]),
            result([]),
            result([]),
            result([]),
        ]
    )

    rows = await get_campaign_dataset(db, user_id=1, campaign_from=2025)

    assert len(rows) == 1
    assert rows[0]["campaign_year"] == 2025


@pytest.mark.asyncio
async def test_get_irrigation_vs_production_analysis() -> None:
    db = MagicMock()

    # Reuse get_campaign_dataset via mocked DB calls (plots, incomes, irrigation, wells, events)
    plot = SimpleNamespace(
        id=1, user_id=1, name="Parcela A", num_plants=100, has_irrigation=True
    )
    incomes = [
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=50.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=60.0
        ),
    ]
    irrigation = [
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2026, 6, 2), water_m3=20.0
        ),
    ]

    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result(incomes),
            result(irrigation),
            result([]),
            result([]),
        ]
    )

    analysis = await get_irrigation_vs_production_analysis(db, user_id=1)

    assert analysis["sample_size"] == 2
    assert analysis["avg_water_m3"] > 0
    assert analysis["avg_production_kg"] > 0
    assert len(analysis["water_bands"]) == 3


@pytest.mark.asyncio
async def test_get_pruning_vs_production_analysis() -> None:
    plot = SimpleNamespace(
        id=1, user_id=1, name="Parcela A", num_plants=100, has_irrigation=True
    )
    income_a = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=80.0
    )
    income_b = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=40.0
    )
    event_pruning = SimpleNamespace(
        user_id=1, plot_id=1, date=datetime.date(2025, 6, 2), event_type="poda"
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plot]),
            result([income_a, income_b]),
            result([]),
            result([]),
            result([event_pruning]),
        ]
    )

    analysis = await get_pruning_vs_production_analysis(db, user_id=1)

    assert analysis["sample_size"] == 2
    assert analysis["with_pruning_count"] == 1
    assert analysis["without_pruning_count"] == 1
    assert analysis["delta_percent"] == 100.0


@pytest.mark.asyncio
async def test_get_tilling_digging_vs_production_analysis() -> None:
    plot = SimpleNamespace(
        id=1, user_id=1, name="Parcela A", num_plants=100, has_irrigation=True
    )
    incomes = [
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=10.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=20.0
        ),
    ]
    events = [
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2026, 6, 2), event_type="labrado"
        ),
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2026, 6, 3), event_type="picado"
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
        ]
    )

    analysis = await get_tilling_digging_vs_production_analysis(db, user_id=1)

    assert analysis["sample_size"] == 2
    assert len(analysis["groups"]) == 4
    assert sum(item["count"] for item in analysis["groups"]) == 2


@pytest.mark.asyncio
async def test_detect_irrigation_thresholds() -> None:
    plot = SimpleNamespace(
        id=1, user_id=1, name="Parcela A", num_plants=100, has_irrigation=True
    )
    incomes = [
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=20.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2026, 6, 1), amount_kg=21.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2027, 6, 1), amount_kg=21.1
        ),
    ]
    irrigation = [
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2026, 6, 2), water_m3=20.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2027, 6, 2), water_m3=30.0
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
        ]
    )

    analysis = await detect_irrigation_thresholds(db, user_id=1)

    assert analysis["sample_size"] == 3
    assert analysis["status"] == "ok"
    assert len(analysis["marginal_gains"]) == 2


@pytest.mark.asyncio
async def test_get_plot_detail_context_found() -> None:
    plot = SimpleNamespace(
        id=10,
        user_id=1,
        name="Parcela Z",
        num_plants=100,
        has_irrigation=True,
        sector="A",
    )
    income = SimpleNamespace(
        user_id=1, plot_id=10, date=datetime.date(2025, 6, 1), amount_kg=42.0
    )
    irrigation = SimpleNamespace(
        user_id=1, plot_id=10, date=datetime.date(2025, 6, 2), water_m3=11.0
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
        ]
    )

    context = await get_plot_detail_context(db, user_id=1, plot_id=10)

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

    context = await get_plot_detail_context(db, user_id=1, plot_id=999)

    assert context is None


@pytest.mark.asyncio
async def test_get_multi_plot_comparison() -> None:
    plot_a = SimpleNamespace(
        id=1, user_id=1, name="Parcela A", num_plants=100, has_irrigation=True
    )
    plot_b = SimpleNamespace(
        id=2, user_id=1, name="Parcela B", num_plants=100, has_irrigation=True
    )
    incomes = [
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2025, 6, 1), amount_kg=40.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=2, date=datetime.date(2025, 6, 1), amount_kg=30.0
        ),
    ]
    irrigation = [
        SimpleNamespace(
            user_id=1, plot_id=1, date=datetime.date(2025, 6, 2), water_m3=10.0
        ),
        SimpleNamespace(
            user_id=1, plot_id=2, date=datetime.date(2025, 6, 2), water_m3=20.0
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
        ]
    )

    comparison = await get_multi_plot_comparison(db, user_id=1)

    assert comparison["sample_size"] == 2
    assert comparison["plots_included"] == 2
    assert len(comparison["points"]) == 2
    assert comparison["efficiency_ranking"][0]["plot_name"] == "Parcela A"

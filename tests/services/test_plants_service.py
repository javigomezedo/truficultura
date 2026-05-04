from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.plant import Plant
from app.models.plot import Plot
from app.services.plants_service import (
    MapRow,
    configure_plot_map,
    get_plant,
    get_plot_map_context,
    has_active_truffle_events,
    list_plants,
)
from tests.conftest import result


# ---------------------------------------------------------------------------
# list_plants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_plants_returns_plants_for_plot() -> None:
    plants = [
        Plant(
            id=1,
            plot_id=10,
            tenant_id=1,
            label="A1",
            row_label="A",
            row_order=0,
            col_order=0,
        ),
        Plant(
            id=2,
            plot_id=10,
            tenant_id=1,
            label="A2",
            row_label="A",
            row_order=0,
            col_order=1,
        ),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(plants))

    found = await list_plants(db, plot_id=10, tenant_id=1)

    assert found == plants


@pytest.mark.asyncio
async def test_list_plants_empty_when_no_plants() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await list_plants(db, plot_id=99, tenant_id=1)

    assert found == []


# ---------------------------------------------------------------------------
# get_plant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_plant_found() -> None:
    plant = Plant(
        id=5, plot_id=10, tenant_id=1, label="B3", row_label="B", row_order=1, col_order=2
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plant]))

    found = await get_plant(db, plant_id=5, tenant_id=1)

    assert found is plant


@pytest.mark.asyncio
async def test_get_plant_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_plant(db, plant_id=999, tenant_id=1)

    assert found is None


# ---------------------------------------------------------------------------
# has_active_truffle_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_active_truffle_events_true_when_event_exists() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([42]))  # event id present

    has = await has_active_truffle_events(db, plot_id=10, tenant_id=1)

    assert has is True


@pytest.mark.asyncio
async def test_has_active_truffle_events_false_when_no_events() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    has = await has_active_truffle_events(db, plot_id=10, tenant_id=1)

    assert has is False


# ---------------------------------------------------------------------------
# configure_plot_map
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_plot_map_creates_correct_plants() -> None:
    plot = Plot(
        id=10,
        tenant_id=1,
        name="P1",
        num_plants=0,
        percentage=100.0,
        planting_date=datetime.date(2020, 1, 1),
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([]),  # has_active_truffle_events → no events
            result([]),  # delete(Plant)
        ]
    )
    db.flush = AsyncMock()
    db.add = MagicMock()

    plants = await configure_plot_map(
        db, plot, tenant_id=1, row_columns=[[1, 2], [1, 2, 3]]
    )

    assert len(plants) == 5
    assert plants[0].label == "A1"
    assert plants[1].label == "A2"
    assert plants[2].label == "B1"
    assert plants[4].label == "B3"
    assert plants[0].visual_col == 1
    assert plants[4].visual_col == 3


@pytest.mark.asyncio
async def test_configure_plot_map_raises_when_events_exist() -> None:
    plot = Plot(
        id=10,
        tenant_id=1,
        name="P1",
        num_plants=5,
        percentage=100.0,
        planting_date=datetime.date(2020, 1, 1),
    )

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([99]))  # event id → blocked

    with pytest.raises(ValueError, match="existen registros de trufas activos"):
        await configure_plot_map(db, plot, tenant_id=1, row_columns=[[1, 2, 3]])


@pytest.mark.asyncio
async def test_configure_plot_map_generates_excel_labels_after_z() -> None:
    plot = Plot(
        id=10,
        tenant_id=1,
        name="P1",
        num_plants=0,
        percentage=100.0,
        planting_date=datetime.date(2020, 1, 1),
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([]),  # has_active_truffle_events -> no events
            result([]),  # delete(Plant)
        ]
    )
    db.flush = AsyncMock()
    db.add = MagicMock()

    plants = await configure_plot_map(
        db, plot, tenant_id=1, row_columns=[[1] for _ in range(28)]
    )

    labels = [p.label for p in plants]
    assert labels[0] == "A1"
    assert labels[25] == "Z1"
    assert labels[26] == "AA1"
    assert labels[27] == "AB1"


# ---------------------------------------------------------------------------
# get_plot_map_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_plot_map_context_no_plants() -> None:
    plot = Plot(id=10, tenant_id=1, name="P1", planting_date=datetime.date(2020, 1, 1))
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    ctx = await get_plot_map_context(db, plot, tenant_id=1, selected_campaign=2025)

    assert ctx["has_plants"] is False
    assert ctx["rows"] == []
    assert ctx["selected_campaign"] == 2025


@pytest.mark.asyncio
async def test_get_plot_map_context_builds_rows_with_weights() -> None:
    plant_a1 = Plant(
        id=1,
        plot_id=10,
        tenant_id=1,
        label="A1",
        row_label="A",
        row_order=0,
        col_order=0,
        visual_col=1,
    )
    plant_a3 = Plant(
        id=2,
        plot_id=10,
        tenant_id=1,
        label="A3",
        row_label="A",
        row_order=0,
        col_order=2,
        visual_col=3,
    )
    plant_b1 = Plant(
        id=3,
        plot_id=10,
        tenant_id=1,
        label="B1",
        row_label="B",
        row_order=1,
        col_order=0,
        visual_col=1,
    )

    total_rows = [
        SimpleNamespace(plant_id=1, total_grams=10.0),
        SimpleNamespace(plant_id=3, total_grams=5.0),
    ]
    campaign_rows = [
        SimpleNamespace(plant_id=1, total_grams=3.0),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plant_a1, plant_a3, plant_b1]),  # plants
            result(total_rows),  # total counts
            result(campaign_rows),  # campaign counts
        ]
    )

    ctx = await get_plot_map_context(
        db,
        Plot(id=10, tenant_id=1, name="X", planting_date=datetime.date(2020, 1, 1)),
        tenant_id=1,
        selected_campaign=2025,
    )

    assert ctx["has_plants"] is True
    rows: list[MapRow] = ctx["rows"]
    assert len(rows) == 2
    assert rows[0].row_label == "A"
    assert len(rows[0].cells) == 3
    assert rows[0].cells[0].campaign_weight_grams == 3.0
    assert rows[0].cells[0].total_weight_grams == 10.0
    assert rows[0].cells[1].plant is None
    assert rows[0].cells[2].campaign_weight_grams == 0.0  # no campaign events for A3
    assert rows[0].cells[2].total_weight_grams == 0.0
    assert rows[1].row_label == "B"
    assert rows[1].cells[0].total_weight_grams == 5.0


@pytest.mark.asyncio
async def test_get_plot_map_context_no_campaign_skips_campaign_query() -> None:
    """When selected_campaign is None only 2 DB queries run (plants + total counts)."""
    plant = Plant(
        id=1, plot_id=10, tenant_id=1, label="A1", row_label="A", row_order=0, col_order=0
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plant]),  # plants
            result([SimpleNamespace(plant_id=1, total_grams=7.0)]),  # total grams
        ]
    )

    ctx = await get_plot_map_context(
        db,
        Plot(id=10, tenant_id=1, name="X", planting_date=datetime.date(2020, 1, 1)),
        tenant_id=1,
        selected_campaign=None,
    )

    assert db.execute.call_count == 2
    assert ctx["rows"][0].cells[0].total_weight_grams == 7.0
    assert ctx["rows"][0].cells[0].campaign_weight_grams == 0.0

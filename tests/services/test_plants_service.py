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
            user_id=1,
            label="A1",
            row_label="A",
            row_order=0,
            col_order=0,
        ),
        Plant(
            id=2,
            plot_id=10,
            user_id=1,
            label="A2",
            row_label="A",
            row_order=0,
            col_order=1,
        ),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(plants))

    found = await list_plants(db, plot_id=10, user_id=1)

    assert found == plants


@pytest.mark.asyncio
async def test_list_plants_empty_when_no_plants() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await list_plants(db, plot_id=99, user_id=1)

    assert found == []


# ---------------------------------------------------------------------------
# get_plant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_plant_found() -> None:
    plant = Plant(
        id=5, plot_id=10, user_id=1, label="B3", row_label="B", row_order=1, col_order=2
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plant]))

    found = await get_plant(db, plant_id=5, user_id=1)

    assert found is plant


@pytest.mark.asyncio
async def test_get_plant_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_plant(db, plant_id=999, user_id=1)

    assert found is None


# ---------------------------------------------------------------------------
# has_active_truffle_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_has_active_truffle_events_true_when_event_exists() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([42]))  # event id present

    has = await has_active_truffle_events(db, plot_id=10, user_id=1)

    assert has is True


@pytest.mark.asyncio
async def test_has_active_truffle_events_false_when_no_events() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    has = await has_active_truffle_events(db, plot_id=10, user_id=1)

    assert has is False


# ---------------------------------------------------------------------------
# configure_plot_map
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_configure_plot_map_creates_correct_plants() -> None:
    plot = Plot(
        id=10,
        user_id=1,
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
            result([plot]),  # _recalculate_percentages fetch plots
        ]
    )
    db.flush = AsyncMock()
    db.add = MagicMock()

    plants = await configure_plot_map(db, plot, user_id=1, row_counts=[2, 3])

    assert len(plants) == 5
    assert plants[0].label == "A1"
    assert plants[1].label == "A2"
    assert plants[2].label == "B1"
    assert plants[4].label == "B3"
    assert plot.num_plants == 5


@pytest.mark.asyncio
async def test_configure_plot_map_raises_when_events_exist() -> None:
    plot = Plot(
        id=10,
        user_id=1,
        name="P1",
        num_plants=5,
        percentage=100.0,
        planting_date=datetime.date(2020, 1, 1),
    )

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([99]))  # event id → blocked

    with pytest.raises(ValueError, match="existen registros de trufas activos"):
        await configure_plot_map(db, plot, user_id=1, row_counts=[3])


# ---------------------------------------------------------------------------
# get_plot_map_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_plot_map_context_no_plants() -> None:
    plot = Plot(id=10, user_id=1, name="P1", planting_date=datetime.date(2020, 1, 1))
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    ctx = await get_plot_map_context(db, plot, user_id=1, selected_campaign=2025)

    assert ctx["has_plants"] is False
    assert ctx["rows"] == []
    assert ctx["selected_campaign"] == 2025


@pytest.mark.asyncio
async def test_get_plot_map_context_builds_rows_with_counts() -> None:
    plant_a1 = Plant(
        id=1, plot_id=10, user_id=1, label="A1", row_label="A", row_order=0, col_order=0
    )
    plant_a2 = Plant(
        id=2, plot_id=10, user_id=1, label="A2", row_label="A", row_order=0, col_order=1
    )
    plant_b1 = Plant(
        id=3, plot_id=10, user_id=1, label="B1", row_label="B", row_order=1, col_order=0
    )

    total_rows = [
        SimpleNamespace(plant_id=1, cnt=10),
        SimpleNamespace(plant_id=3, cnt=5),
    ]
    campaign_rows = [
        SimpleNamespace(plant_id=1, cnt=3),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plant_a1, plant_a2, plant_b1]),  # plants
            result(total_rows),  # total counts
            result(campaign_rows),  # campaign counts
        ]
    )

    ctx = await get_plot_map_context(
        db,
        Plot(id=10, user_id=1, name="X", planting_date=datetime.date(2020, 1, 1)),
        user_id=1,
        selected_campaign=2025,
    )

    assert ctx["has_plants"] is True
    rows: list[MapRow] = ctx["rows"]
    assert len(rows) == 2
    assert rows[0].row_label == "A"
    assert len(rows[0].cells) == 2
    assert rows[0].cells[0].campaign_count == 3
    assert rows[0].cells[0].total_count == 10
    assert rows[0].cells[1].campaign_count == 0  # no campaign events for A2
    assert rows[0].cells[1].total_count == 0
    assert rows[1].row_label == "B"
    assert rows[1].cells[0].total_count == 5


@pytest.mark.asyncio
async def test_get_plot_map_context_no_campaign_skips_campaign_query() -> None:
    """When selected_campaign is None only 2 DB queries run (plants + total counts)."""
    plant = Plant(
        id=1, plot_id=10, user_id=1, label="A1", row_label="A", row_order=0, col_order=0
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result([plant]),  # plants
            result([SimpleNamespace(plant_id=1, cnt=7)]),  # total counts
        ]
    )

    ctx = await get_plot_map_context(
        db,
        Plot(id=10, user_id=1, name="X", planting_date=datetime.date(2020, 1, 1)),
        user_id=1,
        selected_campaign=None,
    )

    assert db.execute.call_count == 2
    assert ctx["rows"][0].cells[0].total_count == 7
    assert ctx["rows"][0].cells[0].campaign_count == 0

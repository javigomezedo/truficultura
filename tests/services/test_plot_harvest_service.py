from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.plot_harvest import PlotHarvest
from app.services.plot_harvest_service import (
    create_harvest,
    create_harvests_batch,
    delete_harvest,
    get_campaign_years,
    get_harvest,
    get_totals_by_plot,
    list_harvests,
    update_harvest,
)
from tests.conftest import result


# ---------------------------------------------------------------------------
# create_harvest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_harvest_stores_fields() -> None:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    h = await create_harvest(
        db,
        user_id=1,
        plot_id=5,
        harvest_date=datetime.date(2025, 11, 10),
        weight_grams=350.0,
        notes="good day",
    )

    assert h.user_id == 1
    assert h.plot_id == 5
    assert h.harvest_date == datetime.date(2025, 11, 10)
    assert h.weight_grams == 350.0
    assert h.notes == "good day"
    db.add.assert_called_once_with(h)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_harvest_clamps_negative_weight() -> None:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    h = await create_harvest(
        db,
        user_id=1,
        plot_id=1,
        harvest_date=datetime.date(2025, 6, 1),
        weight_grams=-100.0,
    )

    assert h.weight_grams == 0.0


# ---------------------------------------------------------------------------
# create_harvests_batch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_harvests_batch_skips_zero_weight() -> None:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    entries = [
        {"plot_id": 1, "harvest_date": datetime.date(2025, 10, 1), "weight_grams": 0},
        {
            "plot_id": 2,
            "harvest_date": datetime.date(2025, 10, 1),
            "weight_grams": 500.0,
        },
    ]
    harvests = await create_harvests_batch(db, user_id=1, entries=entries)

    assert len(harvests) == 1
    assert harvests[0].weight_grams == 500.0
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_harvests_batch_empty_list_no_flush() -> None:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    harvests = await create_harvests_batch(db, user_id=1, entries=[])

    assert harvests == []
    db.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# list_harvests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_harvests_returns_all() -> None:
    h1 = MagicMock(spec=PlotHarvest)
    h2 = MagicMock(spec=PlotHarvest)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([h1, h2]))

    harvests = await list_harvests(db, user_id=1)

    assert harvests == [h1, h2]


# ---------------------------------------------------------------------------
# get_harvest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_harvest_returns_none_when_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    h = await get_harvest(db, harvest_id=99, user_id=1)

    assert h is None


# ---------------------------------------------------------------------------
# update_harvest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_harvest_modifies_fields() -> None:
    existing = PlotHarvest(
        id=1,
        user_id=1,
        plot_id=2,
        harvest_date=datetime.date(2025, 10, 1),
        weight_grams=100.0,
        notes=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([existing]))
    db.flush = AsyncMock()

    updated = await update_harvest(
        db,
        harvest_id=1,
        user_id=1,
        harvest_date=datetime.date(2025, 11, 5),
        weight_grams=250.0,
        notes="updated",
    )

    assert updated is not None
    assert updated.harvest_date == datetime.date(2025, 11, 5)
    assert updated.weight_grams == 250.0
    assert updated.notes == "updated"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_harvest_returns_none_when_missing() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.flush = AsyncMock()

    updated = await update_harvest(db, harvest_id=99, user_id=1, weight_grams=100.0)

    assert updated is None
    db.flush.assert_not_awaited()


# ---------------------------------------------------------------------------
# delete_harvest
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_harvest_returns_true_on_success() -> None:
    existing = PlotHarvest(
        id=1,
        user_id=1,
        plot_id=1,
        harvest_date=datetime.date(2025, 10, 1),
        weight_grams=200.0,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([existing]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    deleted = await delete_harvest(db, harvest_id=1, user_id=1)

    assert deleted is True
    db.delete.assert_awaited_once_with(existing)


@pytest.mark.asyncio
async def test_delete_harvest_returns_false_when_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    deleted = await delete_harvest(db, harvest_id=99, user_id=1)

    assert deleted is False
    db.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# get_totals_by_plot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_totals_by_plot_aggregates_correctly() -> None:
    # Simulate two rows for plot_id=3 and one for plot_id=5
    row1 = SimpleNamespace(plot_id=3, weight_grams=300.0)
    row2 = SimpleNamespace(plot_id=3, weight_grams=150.0)
    row3 = SimpleNamespace(plot_id=5, weight_grams=200.0)
    fake_result = MagicMock()
    fake_result.all.return_value = [row1, row2, row3]
    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    totals = await get_totals_by_plot(db, user_id=1)

    assert totals[3] == pytest.approx(450.0)
    assert totals[5] == pytest.approx(200.0)


# ---------------------------------------------------------------------------
# get_campaign_years
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_campaign_years_returns_sorted_desc() -> None:
    row1 = SimpleNamespace(harvest_date=datetime.date(2025, 11, 1))  # campaign 2025
    row2 = SimpleNamespace(harvest_date=datetime.date(2024, 7, 15))  # campaign 2024
    row3 = SimpleNamespace(
        harvest_date=datetime.date(2025, 3, 10)
    )  # campaign 2024 (Apr still 2024)
    fake_result = MagicMock()
    fake_result.all.return_value = [row1, row2, row3]
    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    years = await get_campaign_years(db, user_id=1)

    assert years == [2025, 2024]

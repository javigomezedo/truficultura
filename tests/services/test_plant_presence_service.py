from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.plant_presence import PlantPresence
from app.services.plant_presence_service import (
    get_campaign_years,
    get_presence_dates_for_plant,
    get_presences_by_plot,
    toggle_presence,
)
from tests.conftest import result


# ---------------------------------------------------------------------------
# toggle_presence — create when absent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_presence_creates_when_absent() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    presence = await toggle_presence(
        db,
        tenant_id=1,
        plant_id=10,
        plot_id=2,
        presence_date=datetime.date(2025, 11, 5),
    )

    assert presence is not None
    assert presence.plant_id == 10
    assert presence.plot_id == 2
    assert presence.has_truffle is True
    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    db.delete.assert_not_awaited()


# ---------------------------------------------------------------------------
# toggle_presence — delete when existing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_presence_deletes_when_existing() -> None:
    existing = PlantPresence(
        id=1,
        tenant_id=1,
        plant_id=10,
        plot_id=2,
        presence_date=datetime.date(2025, 11, 5),
        has_truffle=True,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([existing]))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    result_val = await toggle_presence(
        db,
        tenant_id=1,
        plant_id=10,
        plot_id=2,
        presence_date=datetime.date(2025, 11, 5),
    )

    assert result_val is None
    db.delete.assert_awaited_once_with(existing)
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# get_presences_by_plot
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_presences_by_plot_returns_plant_ids() -> None:
    row1 = SimpleNamespace(plant_id=10)
    row2 = SimpleNamespace(plant_id=20)
    fake_result = MagicMock()
    fake_result.all.return_value = [row1, row2]
    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    presences = await get_presences_by_plot(db, tenant_id=1, plot_id=2)

    assert presences == {10: True, 20: True}


@pytest.mark.asyncio
async def test_get_presences_by_plot_empty() -> None:
    fake_result = MagicMock()
    fake_result.all.return_value = []
    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    presences = await get_presences_by_plot(db, tenant_id=1, plot_id=2)

    assert presences == {}


# ---------------------------------------------------------------------------
# get_presence_dates_for_plant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_presence_dates_sorted_desc() -> None:
    d1 = datetime.date(2025, 11, 5)
    d2 = datetime.date(2025, 11, 1)
    row1 = SimpleNamespace(presence_date=d1)
    row2 = SimpleNamespace(presence_date=d2)
    fake_result = MagicMock()
    fake_result.all.return_value = [row1, row2]
    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    dates = await get_presence_dates_for_plant(db, tenant_id=1, plant_id=10)

    assert dates == [d1, d2]


# ---------------------------------------------------------------------------
# get_campaign_years
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_campaign_years_returns_sorted_desc() -> None:
    row1 = SimpleNamespace(presence_date=datetime.date(2025, 11, 1))  # campaign 2025
    row2 = SimpleNamespace(presence_date=datetime.date(2024, 10, 15))  # campaign 2024
    fake_result = MagicMock()
    fake_result.all.return_value = [row1, row2]
    db = MagicMock()
    db.execute = AsyncMock(return_value=fake_result)

    years = await get_campaign_years(db, tenant_id=1, plot_id=2)

    assert years == [2025, 2024]

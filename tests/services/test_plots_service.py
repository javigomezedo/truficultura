from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.plot import Plot
from app.services.plots_service import (
    create_plot,
    delete_plot,
    get_plot,
    list_plots,
    update_plot,
)
from tests.conftest import result


@pytest.mark.asyncio
async def test_list_plots_returns_ordered_items() -> None:
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=result(
            [Plot(id=1, name="A", planting_date=datetime.date(2020, 1, 1))]
        )
    )

    plots = await list_plots(db, user_id=1)

    assert len(plots) == 1
    assert plots[0].name == "A"


@pytest.mark.asyncio
async def test_get_plot_found_and_not_found() -> None:
    plot = Plot(id=7, name="Norte", planting_date=datetime.date(2019, 4, 1))

    db_found = MagicMock()
    db_found.execute = AsyncMock(return_value=result([plot]))
    assert await get_plot(db_found, 7, user_id=1) is plot

    db_missing = MagicMock()
    db_missing.execute = AsyncMock(return_value=result([]))
    assert await get_plot(db_missing, 8, user_id=1) is None


@pytest.mark.asyncio
async def test_create_update_delete_plot() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    db.execute = AsyncMock(return_value=result([]))

    created = await create_plot(
        db,
        user_id=1,
        name="Bancal Sur",
        polygon="5",
        cadastral_ref="42",
        hydrant="H-01",
        sector="S1",
        num_holm_oaks=120,
        planting_date=datetime.date(2021, 2, 3),
        area_ha=1.5,
        production_start=datetime.date(2024, 1, 1),
    )

    db.add.assert_called_once()
    db.flush.assert_awaited()
    assert created.name == "Bancal Sur"
    assert created.cadastral_ref == "42"

    updated = await update_plot(
        db,
        created,
        name="Bancal Sur 2",
        polygon="6",
        cadastral_ref="43",
        hydrant="H-02",
        sector="S2",
        num_holm_oaks=130,
        planting_date=datetime.date(2021, 3, 3),
        area_ha=1.8,
        production_start=datetime.date(2024, 2, 1),
    )

    assert updated.name == "Bancal Sur 2"
    assert updated.cadastral_ref == "43"

    await delete_plot(db, created)
    db.delete.assert_awaited_once_with(created)

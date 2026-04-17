from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.well import Well
from app.schemas.well import WellCreate, WellUpdate
from app.services.wells_service import (
    create_well,
    delete_well,
    get_well,
    get_well_expenses_for_plot,
    get_wells_list_context,
    list_wells,
    update_well,
)
from tests.conftest import result


@pytest.mark.asyncio
async def test_get_well_found() -> None:
    well = Well(
        id=1,
        user_id=1,
        plot_id=1,
        date=datetime.date(2025, 6, 15),
        wells_per_plant=5,
        expense_id=None,
        notes="Test",
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([well]))

    result_well = await get_well(db, 1, user_id=1)

    assert result_well is well


@pytest.mark.asyncio
async def test_get_well_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    result_well = await get_well(db, 1, user_id=1)

    assert result_well is None


@pytest.mark.asyncio
async def test_list_wells() -> None:
    wells = [
        Well(
            id=1,
            user_id=1,
            plot_id=1,
            date=datetime.date(2025, 6, 15),
            wells_per_plant=5,
            expense_id=None,
            notes=None,
        )
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(wells))

    result_wells = await list_wells(db, user_id=1)

    assert len(result_wells) == 1
    assert result_wells[0].id == 1


@pytest.mark.asyncio
async def test_list_wells_filtered_by_plot() -> None:
    wells = [
        Well(
            id=1,
            user_id=1,
            plot_id=2,
            date=datetime.date(2025, 6, 15),
            wells_per_plant=5,
            expense_id=None,
            notes=None,
        )
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(wells))

    result_wells = await list_wells(db, user_id=1, plot_id=2)

    assert len(result_wells) == 1


@pytest.mark.asyncio
async def test_get_wells_list_context() -> None:
    wells = [
        Well(
            id=1,
            user_id=1,
            plot_id=1,
            date=datetime.date(2025, 6, 15),
            wells_per_plant=5,
            expense_id=None,
            notes=None,
        )
    ]
    plots = [SimpleNamespace(id=1, name="Plot1")]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result(wells), result(plots), result([])])

    context = await get_wells_list_context(db, user_id=1)

    assert "records" in context
    assert len(context["records"]) == 1


@pytest.mark.asyncio
async def test_get_well_expenses_for_plot() -> None:
    expenses = [
        SimpleNamespace(
            id=1, category="Pozos", amount=100.0, date=datetime.date(2025, 6, 15)
        )
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(expenses))

    result_expenses = await get_well_expenses_for_plot(db, user_id=1, plot_id=1)

    assert len(result_expenses) == 1


@pytest.mark.asyncio
async def test_create_well() -> None:
    plot = SimpleNamespace(id=1, name="Plot1")
    db = MagicMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(return_value=result([plot]))

    with patch(
        "app.services.plot_events_service.sync_plot_event_from_well",
        new=AsyncMock(),
    ) as sync_mock:
        well = await create_well(
            db,
            user_id=1,
            data=WellCreate(
                plot_id=1,
                date=datetime.date(2025, 6, 15),
                wells_per_plant=5,
                expense_id=None,
                notes="Test",
            ),
        )

    assert well.user_id == 1
    assert well.wells_per_plant == 5
    db.add.assert_called_once()
    sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_well() -> None:
    existing_well = Well(
        id=1,
        user_id=1,
        plot_id=1,
        date=datetime.date(2025, 6, 15),
        wells_per_plant=5,
        expense_id=None,
        notes="Old",
    )
    db = MagicMock()
    db.flush = AsyncMock()

    with patch(
        "app.services.plot_events_service.sync_plot_event_from_well",
        new=AsyncMock(),
    ) as sync_mock:
        updated_well = await update_well(
            db,
            record=existing_well,
            data=WellUpdate(
                plot_id=None,
                date=datetime.date(2025, 6, 16),
                wells_per_plant=10,
                expense_id=None,
                notes="Updated",
            ),
        )

    assert updated_well.plot_id == 1
    assert updated_well.wells_per_plant == 10
    sync_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_well() -> None:
    well = Well(
        id=1,
        user_id=1,
        plot_id=1,
        date=datetime.date(2025, 6, 15),
        wells_per_plant=5,
        expense_id=None,
        notes=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([well]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    with patch(
        "app.services.plot_events_service.delete_plot_event_for_well",
        new=AsyncMock(),
    ) as delete_event_mock:
        await delete_well(db, 1, user_id=1)

    db.delete.assert_awaited_once_with(well)
    db.flush.assert_awaited_once()
    delete_event_mock.assert_awaited_once_with(db, 1, 1)

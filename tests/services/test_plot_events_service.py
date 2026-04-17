from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.schemas.plot_event import EventType, PlotEventCreate, PlotEventUpdate
from app.services.plot_events_service import (
    create_plot_event,
    delete_plot_event,
    delete_plot_event_for_irrigation,
    delete_plot_event_for_well,
    get_plot_event,
    get_plot_events,
    sync_plot_event_from_irrigation,
    sync_plot_event_from_well,
    update_plot_event,
    validate_one_time_event,
)
from tests.conftest import result


def _make_plot(plot_id: int = 1) -> Plot:
    return Plot(
        id=plot_id,
        user_id=1,
        name=f"Parcela {plot_id}",
        planting_date=datetime.date(2020, 1, 1),
        has_irrigation=True,
        percentage=100.0,
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=100,
    )


def _make_event(event_id: int = 1, event_type: str = "labrado") -> PlotEvent:
    return PlotEvent(
        id=event_id,
        user_id=1,
        plot_id=1,
        event_type=event_type,
        date=datetime.date(2025, 6, 15),
        notes=None,
        is_recurring=True,
        related_irrigation_id=None,
        related_well_id=None,
        created_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc),
    )


@pytest.mark.asyncio
async def test_get_plot_event_found() -> None:
    event = _make_event()
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([event]))

    found = await get_plot_event(db, event_id=1, user_id=1)

    assert found is event


@pytest.mark.asyncio
async def test_get_plot_event_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_plot_event(db, event_id=1, user_id=1)

    assert found is None


@pytest.mark.asyncio
async def test_create_plot_event_success() -> None:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([1]), result([])])
    db.flush = AsyncMock()

    created = await create_plot_event(
        db,
        user_id=1,
        data=PlotEventCreate(
            plot_id=1,
            event_type=EventType.LABRADO,
            date=datetime.date(2025, 6, 15),
            notes="ok",
        ),
    )

    db.add.assert_called_once()
    db.flush.assert_awaited()
    assert created.event_type == EventType.LABRADO.value
    assert created.is_recurring is True


@pytest.mark.asyncio
async def test_validate_one_time_event_duplicate() -> None:
    from fastapi import HTTPException

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([_make_event(event_type="vallado")]))

    with pytest.raises(HTTPException) as exc_info:
        await validate_one_time_event(
            db,
            plot_id=1,
            user_id=1,
            event_type=EventType.VALLADO,
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_update_plot_event() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.flush = AsyncMock()

    event = _make_event(event_type="poda")

    updated = await update_plot_event(
        db,
        event,
        PlotEventUpdate(date=datetime.date(2025, 7, 1), notes="actualizado"),
    )

    assert updated.date == datetime.date(2025, 7, 1)
    assert updated.notes == "actualizado"
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_get_plot_events_filters_by_user_id() -> None:
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=result([_make_event(), _make_event(event_id=2)])
    )

    events = await get_plot_events(db, user_id=1)

    assert len(events) == 2
    where_sql = str(db.execute.call_args[0][0])
    assert "user_id" in where_sql


@pytest.mark.asyncio
async def test_delete_plot_event_success() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([_make_event()]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    await delete_plot_event(db, event_id=1, user_id=1)

    db.delete.assert_awaited_once()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_plot_event_from_irrigation_creates_when_missing() -> None:
    irrigation_record = MagicMock()
    irrigation_record.id = 10
    irrigation_record.user_id = 1
    irrigation_record.plot_id = 2
    irrigation_record.date = datetime.date(2025, 6, 20)
    irrigation_record.notes = "riego"

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.flush = AsyncMock()

    event = await sync_plot_event_from_irrigation(db, irrigation_record)

    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    assert event.related_irrigation_id == 10
    assert event.event_type == EventType.RIEGO.value


@pytest.mark.asyncio
async def test_sync_plot_event_from_well_updates_existing() -> None:
    existing = _make_event(event_type="pozo")
    existing.related_well_id = 15

    well_record = MagicMock()
    well_record.id = 15
    well_record.user_id = 1
    well_record.plot_id = 3
    well_record.date = datetime.date(2025, 8, 1)
    well_record.notes = "pozo actualizado"

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([existing]))
    db.flush = AsyncMock()

    event = await sync_plot_event_from_well(db, well_record)

    assert event.plot_id == 3
    assert event.date == datetime.date(2025, 8, 1)
    assert event.notes == "pozo actualizado"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_plot_event_for_irrigation_and_well() -> None:
    event_irrigation = _make_event(event_type="riego")
    event_well = _make_event(event_id=2, event_type="pozo")
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result([event_irrigation]), result([event_well])]
    )
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    await delete_plot_event_for_irrigation(db, irrigation_id=10, user_id=1)
    await delete_plot_event_for_well(db, well_id=20, user_id=1)

    assert db.delete.await_count == 2
    assert db.flush.await_count == 2

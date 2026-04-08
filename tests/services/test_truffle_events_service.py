from __future__ import annotations

import datetime
from datetime import timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.truffle_event import TruffleEvent
from app.services.truffle_events_service import (
    build_plot_event_summary,
    create_event,
    delete_event,
    get_counts_by_plant,
    get_last_undoable_event,
    list_events,
    undo_last_event,
)
from tests.conftest import result


# ---------------------------------------------------------------------------
# create_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_event_sets_timestamps() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    before = datetime.datetime.now(tz=timezone.utc)
    event = await create_event(db, plant_id=1, plot_id=10, user_id=1, source="manual")
    after = datetime.datetime.now(tz=timezone.utc)

    assert event.plant_id == 1
    assert event.plot_id == 10
    assert event.user_id == 1
    assert event.source == "manual"
    assert before <= event.created_at <= after
    assert event.undo_window_expires_at == event.created_at + timedelta(seconds=30)
    assert event.undone_at is None
    db.execute.assert_awaited_once()
    db.add.assert_called_once_with(event)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_event_default_source_is_manual() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    event = await create_event(db, plant_id=2, plot_id=5, user_id=3)

    assert event.source == "manual"


@pytest.mark.asyncio
async def test_create_event_returns_duplicate_without_creating_new_row() -> None:
    now = datetime.datetime.now(tz=timezone.utc)
    existing = TruffleEvent(
        id=77,
        plant_id=1,
        plot_id=10,
        user_id=1,
        source="manual",
        created_at=now,
        undo_window_expires_at=now + timedelta(seconds=30),
    )

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([existing]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    returned = await create_event(db, plant_id=1, plot_id=10, user_id=1)

    assert returned is existing
    db.add.assert_not_called()
    db.flush.assert_not_called()


# ---------------------------------------------------------------------------
# get_last_undoable_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_last_undoable_event_found_within_window() -> None:
    now = datetime.datetime.now(tz=timezone.utc)
    event = TruffleEvent(
        id=1,
        plant_id=1,
        plot_id=10,
        user_id=1,
        source="manual",
        created_at=now,
        undo_window_expires_at=now + timedelta(seconds=30),
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([event]))

    found = await get_last_undoable_event(db, plant_id=1, user_id=1)

    assert found is event


@pytest.mark.asyncio
async def test_get_last_undoable_event_none_when_no_event() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_last_undoable_event(db, plant_id=99, user_id=1)

    assert found is None


# ---------------------------------------------------------------------------
# undo_last_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_undo_last_event_deletes_record() -> None:
    now = datetime.datetime.now(tz=timezone.utc)
    event = TruffleEvent(
        id=1,
        plant_id=1,
        plot_id=10,
        user_id=1,
        source="qr",
        created_at=now,
        undo_window_expires_at=now + timedelta(seconds=30),
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([event]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    undone = await undo_last_event(db, plant_id=1, user_id=1)

    assert undone is event
    db.delete.assert_awaited_once_with(event)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_undo_last_event_returns_none_when_no_undoable_event() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    undone = await undo_last_event(db, plant_id=1, user_id=1)

    assert undone is None


@pytest.mark.asyncio
async def test_delete_event_deletes_matching_user_record() -> None:
    now = datetime.datetime.now(tz=timezone.utc)
    event = TruffleEvent(
        id=10,
        plant_id=1,
        plot_id=10,
        user_id=1,
        source="manual",
        created_at=now,
        undo_window_expires_at=now + timedelta(seconds=30),
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([event]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    deleted = await delete_event(db, event_id=10, user_id=1)

    assert deleted is True
    db.delete.assert_awaited_once_with(event)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_event_returns_false_when_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    deleted = await delete_event(db, event_id=999, user_id=1)

    assert deleted is False
    db.delete.assert_not_called()
    db.flush.assert_not_called()


# ---------------------------------------------------------------------------
# get_counts_by_plant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_counts_by_plant_returns_dict() -> None:
    rows = [
        SimpleNamespace(plant_id=1, cnt=7),
        SimpleNamespace(plant_id=2, cnt=3),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(rows))

    counts = await get_counts_by_plant(db, plot_id=10, user_id=1)

    assert counts == {1: 7, 2: 3}


@pytest.mark.asyncio
async def test_get_counts_by_plant_empty_when_no_events() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    counts = await get_counts_by_plant(db, plot_id=10, user_id=1)

    assert counts == {}


@pytest.mark.asyncio
async def test_get_counts_by_plant_passes_campaign_filter() -> None:
    """Verify that the campaign_year parameter is accepted (no crash, query executed)."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    counts = await get_counts_by_plant(db, plot_id=10, user_id=1, campaign_year=2025)

    assert counts == {}
    db.execute.assert_awaited_once()


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_events_returns_events() -> None:
    now = datetime.datetime.now(tz=timezone.utc)
    events = [
        TruffleEvent(
            id=1,
            plant_id=1,
            plot_id=10,
            user_id=1,
            source="manual",
            created_at=now,
            undo_window_expires_at=now + timedelta(seconds=30),
        ),
        TruffleEvent(
            id=2,
            plant_id=2,
            plot_id=10,
            user_id=1,
            source="qr",
            created_at=now,
            undo_window_expires_at=now + timedelta(seconds=30),
        ),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(events))

    found = await list_events(db, user_id=1)

    assert found == events


@pytest.mark.asyncio
async def test_list_events_empty_when_none() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await list_events(db, user_id=1, plot_id=10, campaign_year=2025)

    assert found == []


@pytest.mark.asyncio
async def test_list_events_user_id_isolation() -> None:
    """list_events for user 1 and user 2 each trigger separate queries."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    await list_events(db, user_id=1)
    await list_events(db, user_id=2)

    assert db.execute.call_count == 2


@pytest.mark.asyncio
async def test_list_events_can_exclude_undone() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await list_events(db, user_id=1, include_undone=False)

    assert found == []
    db.execute.assert_awaited_once()


def test_build_plot_event_summary_returns_expected_rows() -> None:
    filtered_events = [
        SimpleNamespace(
            plot_id=10,
            plant_id=1,
            undone_at=None,
            plot=SimpleNamespace(name="P1"),
            plant=SimpleNamespace(label="A1"),
        ),
        SimpleNamespace(
            plot_id=10,
            plant_id=2,
            undone_at=None,
            plot=SimpleNamespace(name="P1"),
            plant=SimpleNamespace(label="A2"),
        ),
        SimpleNamespace(
            plot_id=11,
            plant_id=3,
            undone_at=datetime.datetime.now(tz=timezone.utc),
            plot=SimpleNamespace(name="P2"),
            plant=SimpleNamespace(label="B1"),
        ),
    ]
    historical_active_events = [
        SimpleNamespace(
            plot_id=10,
            plant_id=1,
            undone_at=None,
            plot=SimpleNamespace(name="P1"),
            plant=SimpleNamespace(label="A1"),
        ),
        SimpleNamespace(
            plot_id=10,
            plant_id=1,
            undone_at=None,
            plot=SimpleNamespace(name="P1"),
            plant=SimpleNamespace(label="A1"),
        ),
        SimpleNamespace(
            plot_id=10,
            plant_id=2,
            undone_at=None,
            plot=SimpleNamespace(name="P1"),
            plant=SimpleNamespace(label="A2"),
        ),
    ]

    summary = build_plot_event_summary(filtered_events, historical_active_events)

    assert len(summary) == 1
    assert summary[0]["plot_name"] == "P1"
    assert summary[0]["campaign_total"] == 2
    assert summary[0]["historical_total"] == 3
    assert summary[0]["top_plants"][0] == ("A1", 2)

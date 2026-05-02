from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import result


def _fake_datetime_module(fake_today: datetime.date):
    """Return a drop-in replacement for the `datetime` module with a fixed today()."""

    class _FakeDate:
        @staticmethod
        def today() -> datetime.date:
            return fake_today

        def __new__(cls, year: int, month: int, day: int) -> datetime.date:  # type: ignore[misc]
            return datetime.date(year, month, day)

    class _FakeDatetimeModule:
        date = _FakeDate

    return _FakeDatetimeModule()


@pytest.fixture
def db():
    mock = MagicMock()
    mock.execute = AsyncMock()
    mock.flush = AsyncMock()
    mock.delete = AsyncMock()
    mock.add = MagicMock()
    return mock


def _make_recurring(
    id=1,
    tenant_id=1,
    description="Regadío Social",
    amount=50.0,
    category="Regadío Social",
    plot_id=None,
    person="",
    frequency="monthly",
    is_active=True,
    last_run_date=None,
):
    from app.models.recurring_expense import RecurringExpense

    obj = RecurringExpense()
    obj.id = id
    obj.tenant_id = tenant_id
    obj.description = description
    obj.amount = amount
    obj.category = category
    obj.plot_id = plot_id
    obj.person = person
    obj.frequency = frequency
    obj.is_active = is_active
    obj.last_run_date = last_run_date
    return obj


# ---------------------------------------------------------------------------
# list_recurring_expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_recurring_expenses_returns_user_items(db):
    from app.services.recurring_expenses_service import list_recurring_expenses

    rec = _make_recurring()
    db.execute = AsyncMock(return_value=result([rec]))

    items = await list_recurring_expenses(db, tenant_id=1)

    assert items == [rec]
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_recurring_expenses_empty(db):
    from app.services.recurring_expenses_service import list_recurring_expenses

    db.execute = AsyncMock(return_value=result([]))

    items = await list_recurring_expenses(db, tenant_id=1)

    assert items == []


# ---------------------------------------------------------------------------
# get_recurring_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_recurring_expense_found(db):
    from app.services.recurring_expenses_service import get_recurring_expense

    rec = _make_recurring(id=5)
    db.execute = AsyncMock(return_value=result([rec]))

    found = await get_recurring_expense(db, recurring_expense_id=5, tenant_id=1)

    assert found is rec


@pytest.mark.asyncio
async def test_get_recurring_expense_not_found(db):
    from app.services.recurring_expenses_service import get_recurring_expense

    db.execute = AsyncMock(return_value=result([]))

    found = await get_recurring_expense(db, recurring_expense_id=99, tenant_id=1)

    assert found is None


# ---------------------------------------------------------------------------
# create_recurring_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_recurring_expense(db):
    from app.services.recurring_expenses_service import create_recurring_expense

    obj = await create_recurring_expense(
        db,
        tenant_id=1,
        description="Regadío Social",
        amount=55.0,
        category="Regadío Social",
        plot_id=None,
        person="",
        frequency="monthly",
    )

    db.add.assert_called_once_with(obj)
    db.flush.assert_awaited_once()
    assert obj.tenant_id == 1
    assert obj.description == "Regadío Social"
    assert obj.amount == 55.0
    assert obj.frequency == "monthly"
    assert obj.is_active is True
    assert obj.last_run_date is None


@pytest.mark.asyncio
async def test_create_recurring_expense_unknown_frequency_defaults_monthly(db):
    from app.services.recurring_expenses_service import create_recurring_expense

    obj = await create_recurring_expense(
        db,
        tenant_id=1,
        description="Test",
        amount=10.0,
        frequency="fortnightly",  # unknown value
    )

    assert obj.frequency == "monthly"


# ---------------------------------------------------------------------------
# update_recurring_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_recurring_expense(db):
    from app.services.recurring_expenses_service import update_recurring_expense

    rec = _make_recurring(frequency="monthly", is_active=True)

    updated = await update_recurring_expense(
        db,
        rec,
        description="Nuevo concepto",
        amount=99.0,
        category="Otros",
        plot_id=None,
        person="Pepe",
        frequency="annual",
        is_active=False,
    )

    db.flush.assert_awaited_once()
    assert updated.description == "Nuevo concepto"
    assert updated.amount == 99.0
    assert updated.frequency == "annual"
    assert updated.is_active is False
    assert updated.person == "Pepe"


# ---------------------------------------------------------------------------
# delete_recurring_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_recurring_expense(db):
    from app.services.recurring_expenses_service import delete_recurring_expense

    rec = _make_recurring()

    await delete_recurring_expense(db, rec)

    db.delete.assert_awaited_once_with(rec)
    db.flush.assert_awaited_once()


# ---------------------------------------------------------------------------
# toggle_recurring_expense
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_toggle_recurring_expense_active_to_inactive(db):
    from app.services.recurring_expenses_service import toggle_recurring_expense

    rec = _make_recurring(is_active=True)

    updated = await toggle_recurring_expense(db, rec)

    assert updated.is_active is False
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_toggle_recurring_expense_inactive_to_active(db):
    from app.services.recurring_expenses_service import toggle_recurring_expense

    rec = _make_recurring(is_active=False)

    updated = await toggle_recurring_expense(db, rec)

    assert updated.is_active is True


# ---------------------------------------------------------------------------
# process_recurring_expenses
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_no_actives(db):
    from app.services.recurring_expenses_service import process_recurring_expenses

    db.execute = AsyncMock(return_value=result([]))

    created = await process_recurring_expenses(db)

    assert created == []
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_process_day_reached_creates_expense(db, monkeypatch):
    from app.services import recurring_expenses_service

    today = datetime.date(2026, 4, 20)
    monkeypatch.setattr(
        recurring_expenses_service,
        "datetime",
        _fake_datetime_module(today),
    )

    rec = _make_recurring(frequency="monthly", is_active=True, last_run_date=None)
    db.execute = AsyncMock(return_value=result([rec]))

    created = await recurring_expenses_service.process_recurring_expenses(db)

    assert len(created) == 1
    expense = created[0]
    assert expense.description == rec.description
    assert expense.amount == rec.amount
    assert expense.date == today
    assert rec.last_run_date == today
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_already_run_this_month_no_duplicate(db, monkeypatch):
    from app.services import recurring_expenses_service

    today = datetime.date(2026, 4, 20)
    monkeypatch.setattr(
        recurring_expenses_service,
        "datetime",
        _fake_datetime_module(today),
    )

    rec = _make_recurring(
        frequency="monthly",
        is_active=True,
        last_run_date=datetime.date(2026, 4, 1),
    )
    db.execute = AsyncMock(return_value=result([rec]))

    created = await recurring_expenses_service.process_recurring_expenses(db)

    assert created == []
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_process_weekly_creates_after_7_days(db, monkeypatch):
    from app.services import recurring_expenses_service

    today = datetime.date(2026, 4, 20)
    monkeypatch.setattr(
        recurring_expenses_service,
        "datetime",
        _fake_datetime_module(today),
    )

    rec = _make_recurring(
        frequency="weekly",
        is_active=True,
        last_run_date=datetime.date(2026, 4, 13),  # exactly 7 days ago
    )
    db.execute = AsyncMock(return_value=result([rec]))

    created = await recurring_expenses_service.process_recurring_expenses(db)

    assert len(created) == 1
    assert rec.last_run_date == today


@pytest.mark.asyncio
async def test_process_weekly_no_duplicate_within_7_days(db, monkeypatch):
    from app.services import recurring_expenses_service

    today = datetime.date(2026, 4, 20)
    monkeypatch.setattr(
        recurring_expenses_service,
        "datetime",
        _fake_datetime_module(today),
    )

    rec = _make_recurring(
        frequency="weekly",
        is_active=True,
        last_run_date=datetime.date(2026, 4, 15),  # only 5 days ago
    )
    db.execute = AsyncMock(return_value=result([rec]))

    created = await recurring_expenses_service.process_recurring_expenses(db)

    assert created == []
    db.add.assert_not_called()


@pytest.mark.asyncio
async def test_process_retroactive_previous_month(db, monkeypatch):
    """If last_run_date is from a previous month, creates expense."""
    from app.services import recurring_expenses_service

    today = datetime.date(2026, 4, 20)
    monkeypatch.setattr(
        recurring_expenses_service,
        "datetime",
        _fake_datetime_module(today),
    )

    rec = _make_recurring(
        frequency="monthly",
        is_active=True,
        last_run_date=datetime.date(2026, 3, 1),  # ran last month
    )
    db.execute = AsyncMock(return_value=result([rec]))

    created = await recurring_expenses_service.process_recurring_expenses(db)

    assert len(created) == 1
    assert rec.last_run_date == today


@pytest.mark.asyncio
async def test_process_annual_creates_in_new_year(db, monkeypatch):
    from app.services import recurring_expenses_service

    today = datetime.date(2026, 1, 1)
    monkeypatch.setattr(
        recurring_expenses_service,
        "datetime",
        _fake_datetime_module(today),
    )

    rec = _make_recurring(
        frequency="annual",
        is_active=True,
        last_run_date=datetime.date(2025, 1, 1),  # ran last year
    )
    db.execute = AsyncMock(return_value=result([rec]))

    created = await recurring_expenses_service.process_recurring_expenses(db)

    assert len(created) == 1
    assert rec.last_run_date == today


@pytest.mark.asyncio
async def test_process_annual_no_duplicate_same_year(db, monkeypatch):
    from app.services import recurring_expenses_service

    today = datetime.date(2026, 4, 20)
    monkeypatch.setattr(
        recurring_expenses_service,
        "datetime",
        _fake_datetime_module(today),
    )

    rec = _make_recurring(
        frequency="annual",
        is_active=True,
        last_run_date=datetime.date(2026, 1, 1),  # already ran this year
    )
    db.execute = AsyncMock(return_value=result([rec]))

    created = await recurring_expenses_service.process_recurring_expenses(db)

    assert created == []
    db.add.assert_not_called()

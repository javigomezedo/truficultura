from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.expense import Expense
from app.models.income import Income
from app.services.expenses_service import (
    create_expense,
    delete_expense,
    get_expense,
    get_expenses_list_context,
    update_expense,
)
from app.services.incomes_service import (
    create_income,
    delete_income,
    get_income,
    get_incomes_list_context,
    update_income,
)
from tests.conftest import result


@pytest.mark.asyncio
async def test_expenses_list_context_filters_by_campaign() -> None:
    expenses = [
        Expense(id=1, date=datetime.date(2025, 5, 1), description="A", amount=10.0),
        Expense(id=2, date=datetime.date(2026, 2, 1), description="B", amount=5.0),
    ]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result(expenses), result([])])

    context = await get_expenses_list_context(db, 2025, user_id=1)

    assert context["selected_year"] == 2025
    assert len(context["expenses"]) == 2
    assert context["total"] == 15.0
    assert 2025 in context["years"]


@pytest.mark.asyncio
async def test_incomes_list_context_filters_by_campaign() -> None:
    incomes = [
        Income(
            id=1,
            date=datetime.date(2025, 6, 1),
            amount_kg=2.0,
            euros_per_kg=10.0,
            total=20.0,
        ),
        Income(
            id=2,
            date=datetime.date(2026, 1, 15),
            amount_kg=1.0,
            euros_per_kg=15.0,
            total=15.0,
        ),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(incomes))

    context = await get_incomes_list_context(db, 2025, user_id=1)

    assert context["selected_year"] == 2025
    assert len(context["incomes"]) == 2
    assert context["total_kg"] == 3.0
    assert context["total_euros"] == 35.0


@pytest.mark.asyncio
async def test_create_update_delete_expense() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    expense = await create_expense(
        db,
        date=datetime.date(2025, 7, 1),
        description="Riego",
        person="Javi",
        plot_id=1,
        amount=50.0,
        user_id=1,
    )
    assert expense.plot_id == 1

    await update_expense(
        db,
        expense,
        date=datetime.date(2025, 8, 1),
        description="Riego 2",
        person="Javi",
        plot_id=None,
        amount=75.0,
        user_id=1,
    )
    assert expense.plot_id is None
    assert expense.amount == 75.0

    await delete_expense(db, expense, user_id=1)
    db.delete.assert_awaited_once_with(expense)


@pytest.mark.asyncio
async def test_create_update_delete_income() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    income = await create_income(
        db,
        date=datetime.date(2025, 11, 1),
        plot_id=2,
        amount_kg=3.0,
        category="A",
        euros_per_kg=100.0,
        user_id=1,
    )
    assert income.total == 300.0

    await update_income(
        db,
        income,
        date=datetime.date(2025, 11, 2),
        plot_id=None,
        amount_kg=4.0,
        category="B",
        euros_per_kg=80.0,
        user_id=1,
    )
    assert income.total == 320.0
    assert income.plot_id is None

    await delete_income(db, income, user_id=1)
    db.delete.assert_awaited_once_with(income)


@pytest.mark.asyncio
async def test_get_expense_and_get_income() -> None:
    expense = Expense(
        id=10, date=datetime.date(2025, 1, 1), description="X", amount=1.0
    )
    income = Income(
        id=20,
        date=datetime.date(2025, 1, 1),
        amount_kg=1.0,
        euros_per_kg=1.0,
        total=1.0,
    )

    db_e = MagicMock()
    db_e.execute = AsyncMock(return_value=result([expense]))
    assert await get_expense(db_e, 10, user_id=1) is expense

    db_i = MagicMock()
    db_i.execute = AsyncMock(return_value=result([income]))
    assert await get_income(db_i, 20, user_id=1) is income

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.expense import Expense
from app.models.income import Income
from app.models.plot import Plot
from app.models.well import Well
from app.services.dashboard_service import build_dashboard_context
from app.services.reports_service import build_profitability_context
from tests.conftest import result


@pytest.mark.asyncio
async def test_build_dashboard_context_returns_expected_totals() -> None:
    plots = [
        Plot(
            id=1,
            name="P1",
            planting_date=datetime.date(2020, 1, 1),
            percentage=60.0,
            num_plants=10,
        ),
        Plot(
            id=2,
            name="P2",
            planting_date=datetime.date(2020, 1, 1),
            percentage=40.0,
            num_plants=20,
        ),
    ]
    expenses = [
        Expense(
            id=1,
            date=datetime.date(2025, 5, 1),
            description="A",
            plot_id=1,
            amount=100.0,
        ),
        Expense(
            id=2,
            date=datetime.date(2025, 5, 2),
            description="B",
            plot_id=None,
            amount=50.0,
        ),
    ]
    incomes = [
        Income(
            id=1,
            date=datetime.date(2025, 6, 1),
            plot_id=1,
            amount_kg=2.0,
            euros_per_kg=20.0,
            total=40.0,
        ),
        Income(
            id=2,
            date=datetime.date(2025, 6, 2),
            plot_id=2,
            amount_kg=1.0,
            euros_per_kg=30.0,
            total=30.0,
        ),
    ]

    wells = [
        Well(
            id=1,
            user_id=1,
            plot_id=1,
            date=datetime.date(2025, 6, 10),
            wells_per_plant=3,
            expense_id=None,
            notes=None,
        )
    ]
    wells[0].plot = plots[0]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result(plots), result(expenses), result(incomes), result(wells)]
    )

    context = await build_dashboard_context(db, user_id=1)

    assert context["total_plots"] == 2
    assert context["grand_expenses"] == 150.0
    assert context["grand_incomes"] == 70.0
    assert context["grand_profitability"] == -80.0
    assert context["total_wells_per_plant"] == 3
    assert context["total_estimated_wells"] == 30
    assert context["total_well_events"] == 1
    assert len(context["campaign_rows"]) == 1


@pytest.mark.asyncio
async def test_build_profitability_context_returns_matrix() -> None:
    plots = [
        Plot(
            id=1,
            name="P1",
            planting_date=datetime.date(2020, 1, 1),
            percentage=100.0,
        ),
    ]
    incomes = [
        Income(
            id=1,
            date=datetime.date(2025, 12, 1),
            plot_id=1,
            amount_kg=1.0,
            euros_per_kg=10.0,
            total=10.0,
        ),
    ]
    expenses = [
        Expense(
            id=1,
            date=datetime.date(2025, 12, 2),
            description="R",
            plot_id=1,
            amount=3.0,
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result(plots), result(incomes), result(expenses)]
    )

    context = await build_profitability_context(db, user_id=1)

    assert context["all_years"] == [2025]
    assert context["grand_total_incomes"] == 10.0
    assert context["grand_total_expenses"] == 3.0
    assert context["grand_total_profitability"] == 7.0
    assert len(context["matrix"]) == 1

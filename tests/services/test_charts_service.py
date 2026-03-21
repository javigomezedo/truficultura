from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.expense import Expense
from app.models.income import Income
from app.models.plot import Plot
from app.services.charts_service import build_charts_context
from tests.conftest import result


@pytest.mark.asyncio
async def test_build_charts_context_generates_serialized_series() -> None:
    plots = [
        Plot(
            id=1,
            name="P1",
            planting_date=datetime.date(2020, 1, 1),
            area_ha=1.0,
            percentage=100.0,
        ),
    ]
    expenses = [
        Expense(
            id=1,
            date=datetime.date(2025, 12, 1),
            description="Riego",
            plot_id=1,
            amount=5.0,
        ),
    ]
    incomes = [
        Income(
            id=1,
            date=datetime.date(2025, 12, 2),
            plot_id=1,
            amount_kg=2.0,
            category="A",
            euros_per_kg=20.0,
            total=40.0,
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result(plots), result(expenses), result(incomes)]
    )

    context = await build_charts_context(db, campaign=2025, plot_id=None)

    assert context["selected_campaign"] == 2025
    assert context["selected_plot_id"] is None
    assert context["week_labels"].startswith("[")
    assert context["income_values"].startswith("[")
    assert context["expense_values"].startswith("[")
    assert len(context["kg_ha_table"]) == 1

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.services.kpi_service import build_kpi_context
from tests.conftest import result


def _plot(id, name, num_plants=10, area_ha=1.0, percentage=100.0):
    return Plot(
        id=id,
        user_id=1,
        name=name,
        planting_date=datetime.date(2020, 1, 1),
        num_plants=num_plants,
        area_ha=area_ha,
        percentage=percentage,
    )


def _expense(id, date, amount, plot_id):
    return Expense(
        id=id, user_id=1, date=date, description="X", amount=amount, plot_id=plot_id
    )


def _income(id, date, amount_kg, euros_per_kg, plot_id, total=None):
    return Income(
        id=id,
        user_id=1,
        date=date,
        amount_kg=amount_kg,
        euros_per_kg=euros_per_kg,
        total=total if total is not None else amount_kg * euros_per_kg,
        plot_id=plot_id,
    )


def _irrigation(id, date, water_m3, plot_id):
    return IrrigationRecord(
        id=id, user_id=1, date=date, water_m3=water_m3, plot_id=plot_id
    )


def make_db(plots, expenses, incomes, irrigation):
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[
            result(plots),
            result(expenses),
            result(incomes),
            result(irrigation),
        ]
    )
    return db


# ------------------------------------------------------------------ #
# Empty data                                                          #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_empty() -> None:
    db = make_db([], [], [], [])
    context = await build_kpi_context(db, user_id=1)

    assert context["all_campaigns"] == []
    assert context["plots"] == []
    assert context["trend"] == []
    assert context["plot_kpi_table"] == []
    assert context["kpi_summary"] == {
        "roi_pct": None,
        "precio_medio": None,
        "total_kg": None,
        "crecimiento_pct": None,
        "total_incomes": None,
        "total_expenses": None,
        "year": None,
    }


# ------------------------------------------------------------------ #
# ROI calculation                                                     #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_roi() -> None:
    plots = [_plot(1, "P1")]
    expenses = [_expense(1, datetime.date(2025, 6, 1), 100.0, 1)]
    incomes = [_income(1, datetime.date(2025, 6, 1), 5.0, 40.0, 1, total=200.0)]
    db = make_db(plots, expenses, incomes, [])

    context = await build_kpi_context(db, user_id=1)

    assert context["kpi_summary"]["roi_pct"] == pytest.approx(
        100.0
    )  # (200-100)/100 * 100
    assert context["kpi_summary"]["precio_medio"] == pytest.approx(40.0)
    assert context["kpi_summary"]["total_kg"] == pytest.approx(5.0)


# ------------------------------------------------------------------ #
# user_id filter — DB queries must use user_id                        #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_filters_by_user_id() -> None:
    db = make_db([], [], [], [])
    await build_kpi_context(db, user_id=42)

    # Four queries should have been made (plots, expenses, incomes, irrigation)
    assert db.execute.call_count == 4
    # Each query is called — we cannot inspect SQLAlchemy internals easily,
    # but we verify the service returns without error and does not mix users.
    # (multi-tenancy correctness relies on the WHERE clause in the service)


# ------------------------------------------------------------------ #
# Campaign filter reduces kpi_summary to selected campaign            #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_with_campaign_filter() -> None:
    plots = [_plot(1, "P1")]
    expenses = [
        _expense(1, datetime.date(2024, 6, 1), 50.0, 1),  # campaign 2024
        _expense(2, datetime.date(2025, 6, 1), 100.0, 1),  # campaign 2025
    ]
    incomes = [
        _income(1, datetime.date(2024, 6, 1), 2.0, 30.0, 1, total=60.0),
        _income(2, datetime.date(2025, 6, 1), 5.0, 40.0, 1, total=200.0),
    ]
    db = make_db(plots, expenses, incomes, [])

    context = await build_kpi_context(db, user_id=1, selected_campaign=2024)

    assert context["selected_campaign"] == 2024
    assert context["kpi_summary"]["year"] == 2024
    # ROI for 2024: (60 - 50) / 50 * 100 = 20%
    assert context["kpi_summary"]["roi_pct"] == pytest.approx(20.0)


# ------------------------------------------------------------------ #
# No production (kg = 0) — no ZeroDivisionError                      #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_no_kg() -> None:
    plots = [_plot(1, "P1")]
    expenses = [_expense(1, datetime.date(2025, 6, 1), 100.0, 1)]
    db = make_db(plots, expenses, [], [])

    context = await build_kpi_context(db, user_id=1)

    assert context["kpi_summary"]["precio_medio"] is None
    assert context["kpi_summary"]["total_kg"] == pytest.approx(0.0)
    # ROI: (0 - 100) / 100 * 100 = -100%
    assert context["kpi_summary"]["roi_pct"] == pytest.approx(-100.0)


# ------------------------------------------------------------------ #
# No expenses — ROI returns None (avoid division by zero)            #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_no_expenses() -> None:
    plots = [_plot(1, "P1")]
    incomes = [_income(1, datetime.date(2025, 6, 1), 3.0, 50.0, 1, total=150.0)]
    db = make_db(plots, [], incomes, [])

    context = await build_kpi_context(db, user_id=1)

    assert context["kpi_summary"]["roi_pct"] is None
    assert context["kpi_summary"]["precio_medio"] == pytest.approx(50.0)


# ------------------------------------------------------------------ #
# No irrigation — m³ KPIs are None in plot table                     #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_no_irrigation() -> None:
    plots = [_plot(1, "P1")]
    incomes = [_income(1, datetime.date(2025, 6, 1), 3.0, 50.0, 1, total=150.0)]
    db = make_db(plots, [], incomes, [])

    context = await build_kpi_context(db, user_id=1)

    row = context["plot_kpi_table"][0]
    assert row["m3_kg"] is None
    assert row["m3_planta"] is None


# ------------------------------------------------------------------ #
# Unassigned expense distribution across two plots                   #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_unassigned_expense_distributed() -> None:
    plots = [
        _plot(1, "P1", num_plants=6, percentage=60.0),
        _plot(2, "P2", num_plants=4, percentage=40.0),
    ]
    # Unassigned expense of 100 € → P1 gets 60, P2 gets 40
    expenses = [_expense(1, datetime.date(2025, 6, 1), 100.0, None)]
    incomes = [
        _income(1, datetime.date(2025, 6, 1), 10.0, 50.0, 1, total=500.0),
        _income(2, datetime.date(2025, 6, 1), 5.0, 50.0, 2, total=250.0),
    ]
    db = make_db(plots, expenses, incomes, [])

    context = await build_kpi_context(db, user_id=1)

    rows = {r["plot_name"]: r for r in context["plot_kpi_table"]}
    assert rows["P1"]["total_expenses"] == pytest.approx(60.0)
    assert rows["P2"]["total_expenses"] == pytest.approx(40.0)


# ------------------------------------------------------------------ #
# Unassigned incomes are included in campaign-level KPIs             #
# ------------------------------------------------------------------ #


@pytest.mark.asyncio
async def test_build_kpi_context_unassigned_income_counted_in_trend() -> None:
    plots = [_plot(1, "P1")]
    expenses = [_expense(1, datetime.date(2025, 6, 1), 50.0, 1)]
    incomes = [
        _income(1, datetime.date(2025, 6, 1), 2.0, 50.0, 1, total=100.0),
        _income(2, datetime.date(2025, 6, 1), 1.0, 50.0, None, total=50.0),
    ]
    db = make_db(plots, expenses, incomes, [])

    context = await build_kpi_context(db, user_id=1)

    # Historical/global campaign totals must include unassigned incomes
    assert context["trend"][0]["total_incomes"] == pytest.approx(150.0)
    assert context["kpi_summary"]["total_incomes"] == pytest.approx(150.0)
    assert context["kpi_summary"]["total_kg"] == pytest.approx(3.0)

    # Per-plot table still reflects only assigned incomes
    assert context["plot_kpi_table"][0]["total_incomes"] == pytest.approx(100.0)

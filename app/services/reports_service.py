from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.income import Income
from app.models.plot import Plot
from app.utils import campaign_year, distribute_unassigned_expenses


async def build_profitability_context(db: AsyncSession, tenant_id: int) -> dict:
    plots_result = await db.execute(
        select(Plot).where(Plot.tenant_id == tenant_id).order_by(Plot.name)
    )
    plots = plots_result.scalars().all()

    incomes_result = await db.execute(select(Income).where(Income.tenant_id == tenant_id))
    incomes = incomes_result.scalars().all()

    expenses_result = await db.execute(
        select(Expense).where(Expense.tenant_id == tenant_id)
    )
    expenses = expenses_result.scalars().all()

    incomes_by_year_plot: dict = defaultdict(lambda: defaultdict(float))
    for income in incomes:
        cy = campaign_year(income.date)
        incomes_by_year_plot[cy][income.plot_id] += income.total

    expenses_raw: dict = defaultdict(lambda: defaultdict(float))
    for expense in expenses:
        cy = campaign_year(expense.date)
        expenses_raw[cy][expense.plot_id] += expense.amount

    expenses_by_year_plot = distribute_unassigned_expenses(expenses_raw, plots)

    all_years = sorted(
        set(list(incomes_by_year_plot.keys()) + list(expenses_by_year_plot.keys())),
        reverse=True,
    )

    plot_ids = [plot.id for plot in plots]
    matrix = []
    year_totals = {}
    plot_totals = defaultdict(
        lambda: {"incomes": 0.0, "expenses": 0.0, "profitability": 0.0}
    )

    for year in all_years:
        row = {"year": year, "plots": {}}
        year_income = 0.0
        year_expense = 0.0

        for pid in plot_ids:
            inc = incomes_by_year_plot[year][pid]
            exp = expenses_by_year_plot[year][pid]
            profitability = inc - exp

            row["plots"][pid] = {
                "incomes": inc,
                "expenses": exp,
                "profitability": profitability,
            }

            year_income += inc
            year_expense += exp
            plot_totals[pid]["incomes"] += inc
            plot_totals[pid]["expenses"] += exp
            plot_totals[pid]["profitability"] += profitability

        row["total_incomes"] = year_income
        row["total_expenses"] = year_expense
        row["total_profitability"] = year_income - year_expense
        matrix.append(row)

        year_totals[year] = {
            "incomes": year_income,
            "expenses": year_expense,
            "profitability": year_income - year_expense,
        }

    for pid in plot_ids:
        plot_totals[pid]["profitability"] = (
            plot_totals[pid]["incomes"] - plot_totals[pid]["expenses"]
        )

    grand_total_incomes = sum(yt["incomes"] for yt in year_totals.values())
    grand_total_expenses = sum(yt["expenses"] for yt in year_totals.values())
    grand_total_profitability = grand_total_incomes - grand_total_expenses

    return {
        "plots": plots,
        "all_years": all_years,
        "matrix": matrix,
        "year_totals": year_totals,
        "plot_totals": dict(plot_totals),
        "grand_total_incomes": grand_total_incomes,
        "grand_total_expenses": grand_total_expenses,
        "grand_total_profitability": grand_total_profitability,
    }

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Expense, Income, Plot
from app.utils import campaign_year, distribute_unassigned_expenses


async def build_dashboard_context(db: AsyncSession) -> dict:
    plots_result = await db.execute(select(Plot).order_by(Plot.name))
    all_plots = plots_result.scalars().all()

    expenses_result = await db.execute(select(Expense))
    all_expenses = expenses_result.scalars().all()

    incomes_result = await db.execute(select(Income))
    all_incomes = incomes_result.scalars().all()

    grand_expenses = sum(e.amount for e in all_expenses)
    grand_incomes = sum(i.total for i in all_incomes)
    grand_profitability = grand_incomes - grand_expenses

    expenses_raw: dict = defaultdict(lambda: defaultdict(float))
    for expense in all_expenses:
        expenses_raw[campaign_year(expense.date)][expense.plot_id] += expense.amount

    expenses_by_cy_plot = distribute_unassigned_expenses(expenses_raw, all_plots)

    by_campaign: dict = defaultdict(lambda: {"expenses": 0.0, "incomes": 0.0})
    for cy, by_plot in expenses_by_cy_plot.items():
        by_campaign[cy]["expenses"] += sum(by_plot.values())

    for income in all_incomes:
        by_campaign[campaign_year(income.date)]["incomes"] += income.total

    campaigns = sorted(by_campaign.keys(), reverse=True)
    campaign_rows = [
        {
            "year": cy,
            "expenses": by_campaign[cy]["expenses"],
            "incomes": by_campaign[cy]["incomes"],
            "profitability": by_campaign[cy]["incomes"] - by_campaign[cy]["expenses"],
        }
        for cy in campaigns
    ]

    incomes_by_cy_plot: dict = defaultdict(lambda: defaultdict(float))
    for income in all_incomes:
        incomes_by_cy_plot[campaign_year(income.date)][income.plot_id] += income.total

    matrix = []
    plot_totals: dict = defaultdict(
        lambda: {"incomes": 0.0, "expenses": 0.0, "profitability": 0.0}
    )
    for cy in campaigns:
        row = {"year": cy, "plots": {}}
        for plot in all_plots:
            ing = incomes_by_cy_plot[cy][plot.id]
            exp = expenses_by_cy_plot[cy][plot.id]
            row["plots"][plot.id] = {
                "incomes": ing,
                "expenses": exp,
                "profitability": ing - exp,
            }
            plot_totals[plot.id]["incomes"] += ing
            plot_totals[plot.id]["expenses"] += exp

        row["total_incomes"] = by_campaign[cy]["incomes"]
        row["total_expenses"] = by_campaign[cy]["expenses"]
        row["total_profitability"] = (
            by_campaign[cy]["incomes"] - by_campaign[cy]["expenses"]
        )
        matrix.append(row)

    for pid in plot_totals:
        plot_totals[pid]["profitability"] = (
            plot_totals[pid]["incomes"] - plot_totals[pid]["expenses"]
        )

    return {
        "total_plots": len(all_plots),
        "grand_expenses": grand_expenses,
        "grand_incomes": grand_incomes,
        "grand_profitability": grand_profitability,
        "campaign_rows": campaign_rows,
        "plots": all_plots,
        "matrix": matrix,
        "plot_totals": dict(plot_totals),
    }

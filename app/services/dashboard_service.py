from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import lazyload

from app.models import Expense, Income, Plot, Well
from app.utils import campaign_year, distribute_unassigned_expenses


async def build_dashboard_context(db: AsyncSession, tenant_id: int) -> dict:
    plots_result = await db.execute(
        select(Plot).where(Plot.tenant_id == tenant_id).order_by(Plot.name)
    )
    all_plots = plots_result.scalars().all()

    # Use column-level selects to avoid loading joined relationships and binary data.
    expenses_result = await db.execute(
        select(Expense.date, Expense.amount, Expense.plot_id).where(
            Expense.tenant_id == tenant_id
        )
    )
    expense_rows = expenses_result.all()

    incomes_result = await db.execute(
        select(
            Income.date, Income.amount_kg, Income.euros_per_kg, Income.plot_id
        ).where(Income.tenant_id == tenant_id)
    )
    income_rows = incomes_result.all()

    # For wells we need plot.num_plants (already eagerly joined) but NOT the expense.
    wells_result = await db.execute(
        select(Well).where(Well.tenant_id == tenant_id).options(lazyload(Well.expense))
    )
    all_wells = wells_result.scalars().all()

    grand_expenses = sum(r.amount for r in expense_rows)
    grand_incomes = sum(round(r.amount_kg * r.euros_per_kg, 2) for r in income_rows)
    grand_profitability = grand_incomes - grand_expenses

    total_wells_per_plant = sum(w.wells_per_plant for w in all_wells)
    total_estimated_wells = sum(
        w.wells_per_plant * (w.plot.num_plants if w.plot is not None else 0)
        for w in all_wells
    )
    total_well_events = len(all_wells)

    expenses_raw: dict = defaultdict(lambda: defaultdict(float))
    for r in expense_rows:
        expenses_raw[campaign_year(r.date)][r.plot_id] += r.amount

    expenses_by_cy_plot = distribute_unassigned_expenses(expenses_raw, all_plots)

    by_campaign: dict = defaultdict(lambda: {"expenses": 0.0, "incomes": 0.0})
    for cy, by_plot in expenses_by_cy_plot.items():
        by_campaign[cy]["expenses"] += sum(by_plot.values())

    for r in income_rows:
        by_campaign[campaign_year(r.date)]["incomes"] += round(
            r.amount_kg * r.euros_per_kg, 2
        )

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
    for r in income_rows:
        incomes_by_cy_plot[campaign_year(r.date)][r.plot_id] += round(
            r.amount_kg * r.euros_per_kg, 2
        )

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
        "total_wells_per_plant": total_wells_per_plant,
        "total_estimated_wells": total_estimated_wells,
        "total_well_events": total_well_events,
        "campaign_rows": campaign_rows,
        "plots": all_plots,
        "matrix": matrix,
        "plot_totals": dict(plot_totals),
    }

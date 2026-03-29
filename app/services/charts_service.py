from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.income import Income
from app.models.plot import Plot
from app.utils import campaign_year, distribute_unassigned_expenses

CHART_COLORS = [
    "#198754",
    "#0d6efd",
    "#dc3545",
    "#fd7e14",
    "#6f42c1",
    "#20c997",
    "#ffc107",
]


async def build_charts_context(
    db: AsyncSession,
    campaign: Optional[int],
    plot_id: Optional[int],
    user_id: int,
) -> dict:
    plots_result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    all_plots = plots_result.scalars().all()

    expenses_result = await db.execute(
        select(Expense).where(Expense.user_id == user_id)
    )
    all_expenses = expenses_result.scalars().all()

    incomes_result = await db.execute(select(Income).where(Income.user_id == user_id))
    all_incomes = incomes_result.scalars().all()

    all_campaigns = sorted(
        {campaign_year(i.date) for i in all_incomes}
        | {campaign_year(e.date) for e in all_expenses},
        reverse=True,
    )

    selected_campaign: Optional[int] = campaign

    selected_plot_id: Optional[int] = plot_id

    kg_by_cy_plot: dict = defaultdict(lambda: defaultdict(float))
    for income in all_incomes:
        if income.plot_id is not None:
            kg_by_cy_plot[campaign_year(income.date)][income.plot_id] += (
                income.amount_kg
            )

    kg_ha_table = []
    for cy in all_campaigns:
        row_plots = {}
        for plot in all_plots:
            kg = kg_by_cy_plot[cy][plot.id]
            kg_ha = kg / plot.area_ha if plot.area_ha and plot.area_ha > 0 else None
            row_plots[plot.id] = {"kg": kg, "kg_ha": kg_ha}
        kg_ha_table.append({"year": cy, "plots": row_plots})

    kg_ha_totals = {}
    for plot in all_plots:
        total_kg = sum(kg_by_cy_plot[cy][plot.id] for cy in all_campaigns)
        total_kg_ha = (
            total_kg / plot.area_ha if plot.area_ha and plot.area_ha > 0 else None
        )
        kg_ha_totals[plot.id] = {"kg": total_kg, "kg_ha": total_kg_ha}

    filtered_incomes = [
        income
        for income in all_incomes
        if income.amount_kg > 0
        and (
            selected_campaign is None or campaign_year(income.date) == selected_campaign
        )
        and (selected_plot_id is None or income.plot_id == selected_plot_id)
    ]

    kg_by_week: dict = defaultdict(float)
    total_by_week: dict = defaultdict(float)
    precio_kg_sum: dict = defaultdict(float)
    precio_kg_cnt: dict = defaultdict(float)
    cat_kg_by_week: dict = defaultdict(lambda: defaultdict(float))

    for income in filtered_incomes:
        monday = income.date - timedelta(days=income.date.weekday())
        kg_by_week[monday] += income.amount_kg
        total_by_week[monday] += income.total

        category = income.category if income.category else "Sin cat."
        cat_kg_by_week[category][monday] += income.amount_kg

        if income.euros_per_kg > 0:
            precio_kg_sum[monday] += income.total
            precio_kg_cnt[monday] += income.amount_kg

    sorted_weeks: list = []
    if kg_by_week:
        current = min(kg_by_week.keys())
        last = max(kg_by_week.keys())
        while current <= last:
            sorted_weeks.append(current)
            current += timedelta(weeks=1)

    week_labels = [w.strftime("%d/%m/%Y") for w in sorted_weeks]

    weekly_price = []
    price_week_labels = []
    for week in sorted_weeks:
        cnt = precio_kg_cnt.get(week, 0.0)
        if cnt > 0:
            price_week_labels.append(week.strftime("%d/%m/%Y"))
            weekly_price.append(round(precio_kg_sum[week] / cnt, 2))

    weekly_kg = [round(kg_by_week.get(w, 0.0), 3) for w in sorted_weeks]

    cumulative_income = []
    running = 0.0
    for week in sorted_weeks:
        running += total_by_week.get(week, 0.0)
        cumulative_income.append(round(running, 2))

    all_cats = sorted(cat_kg_by_week.keys())
    cat_datasets = []
    for idx, cat in enumerate(all_cats):
        color = CHART_COLORS[idx % len(CHART_COLORS)]
        data = [round(cat_kg_by_week[cat].get(week, 0.0), 3) for week in sorted_weeks]
        cat_datasets.append({"label": cat, "data": data, "backgroundColor": color})

    filtered_expenses = [
        expense
        for expense in all_expenses
        if selected_campaign is None or campaign_year(expense.date) == selected_campaign
    ]

    expenses_by_category: dict = defaultdict(float)
    for expense in filtered_expenses:
        cat = expense.category if expense.category else "Sin categoría"
        expenses_by_category[cat] += expense.amount

    sorted_cat_exp = sorted(
        expenses_by_category.items(), key=lambda x: x[1], reverse=True
    )
    expense_cat_labels = [item[0] for item in sorted_cat_exp]
    expense_cat_values = [round(item[1], 2) for item in sorted_cat_exp]

    filtered_incomes_bar = [
        income
        for income in all_incomes
        if selected_campaign is None or campaign_year(income.date) == selected_campaign
    ]

    expenses_raw: dict = {0: defaultdict(float)}
    for expense in filtered_expenses:
        expenses_raw[0][expense.plot_id] += expense.amount

    distributed_expenses = distribute_unassigned_expenses(expenses_raw, all_plots)
    expenses_per_plot = distributed_expenses.get(0, {})

    incomes_per_plot: dict = defaultdict(float)
    for income in filtered_incomes_bar:
        if income.plot_id is not None:
            incomes_per_plot[income.plot_id] += income.total

    plot_labels = [plot.name for plot in all_plots]
    income_values = [round(incomes_per_plot.get(plot.id, 0.0), 2) for plot in all_plots]
    expense_values = [
        round(expenses_per_plot.get(plot.id, 0.0), 2) for plot in all_plots
    ]

    return {
        "all_campaigns": all_campaigns,
        "selected_campaign": selected_campaign,
        "all_plots": all_plots,
        "selected_plot_id": selected_plot_id,
        "kg_ha_table": kg_ha_table,
        "kg_ha_totals": kg_ha_totals,
        "week_labels": json.dumps(week_labels),
        "weekly_price": json.dumps(weekly_price),
        "price_week_labels": json.dumps(price_week_labels),
        "weekly_kg": json.dumps(weekly_kg),
        "cumulative_income": json.dumps(cumulative_income),
        "cat_datasets": json.dumps(cat_datasets),
        "plot_labels": json.dumps(plot_labels),
        "income_values": json.dumps(income_values),
        "expense_values": json.dumps(expense_values),
        "expense_cat_labels": json.dumps(expense_cat_labels),
        "expense_cat_values": json.dumps(expense_cat_values),
    }

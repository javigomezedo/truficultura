from __future__ import annotations

import json
from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.utils import campaign_year, distribute_unassigned_expenses


async def build_kpi_context(
    db: AsyncSession,
    user_id: int,
    selected_campaign: Optional[int] = None,
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

    irrigation_result = await db.execute(
        select(IrrigationRecord).where(IrrigationRecord.user_id == user_id)
    )
    all_irrigation = irrigation_result.scalars().all()

    # ------------------------------------------------------------------ #
    # Aggregate campaigns                                                  #
    # ------------------------------------------------------------------ #
    all_campaigns = sorted(
        {campaign_year(i.date) for i in all_incomes}
        | {campaign_year(e.date) for e in all_expenses},
        reverse=True,
    )

    # ------------------------------------------------------------------ #
    # Distribute unassigned expenses                                       #
    # ------------------------------------------------------------------ #
    expenses_raw: dict = defaultdict(lambda: defaultdict(float))
    for expense in all_expenses:
        expenses_raw[campaign_year(expense.date)][expense.plot_id] += expense.amount

    expenses_by_cy_plot = distribute_unassigned_expenses(expenses_raw, all_plots)

    # ------------------------------------------------------------------ #
    # Aggregate incomes: kg and € per (campaign, plot)                    #
    # ------------------------------------------------------------------ #
    kg_by_cy_plot: dict = defaultdict(lambda: defaultdict(float))
    eur_by_cy_plot: dict = defaultdict(lambda: defaultdict(float))
    for income in all_incomes:
        cy = campaign_year(income.date)
        if income.plot_id is not None:
            kg_by_cy_plot[cy][income.plot_id] += income.amount_kg
            eur_by_cy_plot[cy][income.plot_id] += income.total

    # ------------------------------------------------------------------ #
    # Aggregate irrigation: m³ per (campaign, plot)                       #
    # ------------------------------------------------------------------ #
    m3_by_cy_plot: dict = defaultdict(lambda: defaultdict(float))
    for rec in all_irrigation:
        cy = campaign_year(rec.date)
        m3_by_cy_plot[cy][rec.plot_id] += rec.water_m3

    # ------------------------------------------------------------------ #
    # Per-campaign global KPIs (for trend charts)                         #
    # ------------------------------------------------------------------ #
    trend: list[dict] = []
    prev_kg: Optional[float] = None
    for cy in sorted(all_campaigns):
        total_incomes = sum(eur_by_cy_plot[cy].values())
        total_expenses = sum(expenses_by_cy_plot[cy].values())
        total_kg = sum(kg_by_cy_plot[cy].values())
        total_m3 = sum(m3_by_cy_plot[cy].values())

        roi_pct = (
            (total_incomes - total_expenses) / total_expenses * 100.0
            if total_expenses > 0
            else None
        )
        precio_medio = total_incomes / total_kg if total_kg > 0 else None
        m3_por_kg = total_m3 / total_kg if total_kg > 0 and total_m3 > 0 else None
        crecimiento_pct = (
            (total_kg - prev_kg) / prev_kg * 100.0
            if prev_kg is not None and prev_kg > 0
            else None
        )

        trend.append(
            {
                "year": cy,
                "total_kg": total_kg,
                "total_incomes": total_incomes,
                "total_expenses": total_expenses,
                "roi_pct": roi_pct,
                "precio_medio": precio_medio,
                "m3_por_kg": m3_por_kg,
                "crecimiento_pct": crecimiento_pct,
            }
        )
        prev_kg = total_kg

    trend_sorted_desc = list(reversed(trend))

    # ------------------------------------------------------------------ #
    # Summary KPIs — latest campaign (or selected)                        #
    # ------------------------------------------------------------------ #
    if selected_campaign is not None and any(
        t["year"] == selected_campaign for t in trend
    ):
        latest = next(t for t in trend if t["year"] == selected_campaign)
    else:
        latest = trend[-1] if trend else {}

    kpi_summary = {
        "roi_pct": latest.get("roi_pct"),
        "precio_medio": latest.get("precio_medio"),
        "total_kg": latest.get("total_kg"),
        "crecimiento_pct": latest.get("crecimiento_pct"),
        "total_incomes": latest.get("total_incomes"),
        "total_expenses": latest.get("total_expenses"),
        "year": latest.get("year"),
    }

    # ------------------------------------------------------------------ #
    # Chart.js trend data                                                  #
    # ------------------------------------------------------------------ #
    from app.utils import campaign_label

    trend_labels = json.dumps([campaign_label(t["year"]) for t in trend])
    roi_trend = json.dumps(
        [round(t["roi_pct"], 2) if t["roi_pct"] is not None else None for t in trend]
    )
    price_trend = json.dumps(
        [
            round(t["precio_medio"], 2) if t["precio_medio"] is not None else None
            for t in trend
        ]
    )
    kg_trend = json.dumps([round(t["total_kg"], 2) for t in trend])
    m3_kg_trend = json.dumps(
        [
            round(t["m3_por_kg"], 2) if t["m3_por_kg"] is not None else None
            for t in trend
        ]
    )

    # ------------------------------------------------------------------ #
    # Per-plot KPI table (for selected campaign or sum of all campaigns)  #
    # ------------------------------------------------------------------ #
    target_cy = selected_campaign

    plot_kpi_table: list[dict] = []
    plot_names: list[str] = []
    plot_kg_ha_values: list[Optional[float]] = []
    plot_roi_values: list[Optional[float]] = []

    for plot in all_plots:
        if target_cy is not None:
            cycles = [target_cy]
        else:
            cycles = all_campaigns

        total_kg = sum(kg_by_cy_plot[cy][plot.id] for cy in cycles)
        total_eur = sum(eur_by_cy_plot[cy][plot.id] for cy in cycles)
        total_exp = sum(expenses_by_cy_plot[cy][plot.id] for cy in cycles)
        total_m3 = sum(m3_by_cy_plot[cy][plot.id] for cy in cycles)

        kg_ha = (
            total_kg / plot.area_ha
            if plot.area_ha and plot.area_ha > 0 and total_kg > 0
            else None
        )
        kg_planta = (
            total_kg / plot.num_plants
            if plot.num_plants and plot.num_plants > 0 and total_kg > 0
            else None
        )
        coste_kg = total_exp / total_kg if total_kg > 0 and total_exp > 0 else None
        roi_pct = (total_eur - total_exp) / total_exp * 100.0 if total_exp > 0 else None
        m3_kg = total_m3 / total_kg if total_kg > 0 and total_m3 > 0 else None
        m3_planta = (
            total_m3 / plot.num_plants
            if plot.num_plants and plot.num_plants > 0 and total_m3 > 0
            else None
        )

        plot_kpi_table.append(
            {
                "plot_name": plot.name,
                "total_kg": total_kg,
                "total_incomes": total_eur,
                "total_expenses": total_exp,
                "kg_ha": kg_ha,
                "kg_planta": kg_planta,
                "coste_kg": coste_kg,
                "roi_pct": roi_pct,
                "m3_kg": m3_kg,
                "m3_planta": m3_planta,
            }
        )
        plot_names.append(plot.name)
        plot_kg_ha_values.append(round(kg_ha, 2) if kg_ha is not None else None)
        plot_roi_values.append(round(roi_pct, 2) if roi_pct is not None else None)

    return {
        "all_campaigns": all_campaigns,
        "selected_campaign": selected_campaign,
        "plots": all_plots,
        "kpi_summary": kpi_summary,
        "trend": trend_sorted_desc,
        # Chart.js JSON data
        "trend_labels": trend_labels,
        "roi_trend": roi_trend,
        "price_trend": price_trend,
        "kg_trend": kg_trend,
        "m3_kg_trend": m3_kg_trend,
        "plot_kpi_table": plot_kpi_table,
        "plot_labels": json.dumps(plot_names),
        "plot_kg_ha_values": json.dumps(plot_kg_ha_values),
        "plot_roi_values": json.dumps(plot_roi_values),
    }

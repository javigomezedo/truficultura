from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gasto import Gasto
from app.models.ingreso import Ingreso
from app.models.parcela import Parcela
from app.utils import campaign_year, distribute_unassigned_gastos

CHART_COLORS = [
    "#198754",
    "#0d6efd",
    "#dc3545",
    "#fd7e14",
    "#6f42c1",
    "#20c997",
    "#ffc107",
]


async def build_graficas_context(
    db: AsyncSession,
    campaign: Optional[int],
    bancal_id: Optional[int],
) -> dict:
    parcelas_result = await db.execute(select(Parcela).order_by(Parcela.nombre))
    all_parcelas = parcelas_result.scalars().all()

    gastos_result = await db.execute(select(Gasto))
    all_gastos = gastos_result.scalars().all()

    ingresos_result = await db.execute(select(Ingreso))
    all_ingresos = ingresos_result.scalars().all()

    all_campaigns = sorted({campaign_year(i.fecha) for i in all_ingresos}, reverse=True)

    selected_campaign: Optional[int] = campaign
    if selected_campaign is None and all_campaigns:
        selected_campaign = all_campaigns[0]

    selected_bancal: Optional[int] = bancal_id

    kg_by_cy_p: dict = defaultdict(lambda: defaultdict(float))
    for ingreso in all_ingresos:
        if ingreso.parcela_id is not None:
            kg_by_cy_p[campaign_year(ingreso.fecha)][ingreso.parcela_id] += (
                ingreso.cantidad_kg
            )

    kg_ha_table = []
    for cy in all_campaigns:
        row_parcelas = {}
        for parcela in all_parcelas:
            kg = kg_by_cy_p[cy][parcela.id]
            kg_ha = (
                kg / parcela.superficie_ha
                if parcela.superficie_ha and parcela.superficie_ha > 0
                else None
            )
            row_parcelas[parcela.id] = {"kg": kg, "kg_ha": kg_ha}
        kg_ha_table.append({"year": cy, "parcelas": row_parcelas})

    kg_ha_totals = {}
    for parcela in all_parcelas:
        total_kg = sum(kg_by_cy_p[cy][parcela.id] for cy in all_campaigns)
        total_kg_ha = (
            total_kg / parcela.superficie_ha
            if parcela.superficie_ha and parcela.superficie_ha > 0
            else None
        )
        kg_ha_totals[parcela.id] = {"kg": total_kg, "kg_ha": total_kg_ha}

    filtered_ingresos = [
        ingreso
        for ingreso in all_ingresos
        if ingreso.cantidad_kg > 0
        and (
            selected_campaign is None
            or campaign_year(ingreso.fecha) == selected_campaign
        )
        and (selected_bancal is None or ingreso.parcela_id == selected_bancal)
    ]

    kg_by_week: dict = defaultdict(float)
    total_by_week: dict = defaultdict(float)
    precio_kg_sum: dict = defaultdict(float)
    precio_kg_cnt: dict = defaultdict(float)
    cat_kg_by_week: dict = defaultdict(lambda: defaultdict(float))

    for ingreso in filtered_ingresos:
        monday = ingreso.fecha - timedelta(days=ingreso.fecha.weekday())
        kg_by_week[monday] += ingreso.cantidad_kg
        total_by_week[monday] += ingreso.total

        categoria = ingreso.categoria if ingreso.categoria else "Sin cat."
        cat_kg_by_week[categoria][monday] += ingreso.cantidad_kg

        if ingreso.euros_kg > 0:
            precio_kg_sum[monday] += ingreso.total
            precio_kg_cnt[monday] += ingreso.cantidad_kg

    sorted_weeks: list = []
    if kg_by_week:
        current = min(kg_by_week.keys())
        last = max(kg_by_week.keys())
        while current <= last:
            sorted_weeks.append(current)
            current += timedelta(weeks=1)

    week_labels = [w.strftime("%d/%m/%Y") for w in sorted_weeks]

    precio_semanal = []
    for week in sorted_weeks:
        cnt = precio_kg_cnt.get(week, 0.0)
        total = precio_kg_sum.get(week, 0.0)
        precio_semanal.append(round(total / cnt, 2) if cnt > 0 else 0)

    kg_semanal = [round(kg_by_week.get(w, 0.0), 3) for w in sorted_weeks]

    ingresos_acumulados = []
    running = 0.0
    for week in sorted_weeks:
        running += total_by_week.get(week, 0.0)
        ingresos_acumulados.append(round(running, 2))

    all_cats = sorted(cat_kg_by_week.keys())
    cat_datasets = []
    for idx, cat in enumerate(all_cats):
        color = CHART_COLORS[idx % len(CHART_COLORS)]
        data = [round(cat_kg_by_week[cat].get(week, 0.0), 3) for week in sorted_weeks]
        cat_datasets.append({"label": cat, "data": data, "backgroundColor": color})

    filtered_gastos = [
        gasto
        for gasto in all_gastos
        if selected_campaign is None or campaign_year(gasto.fecha) == selected_campaign
    ]
    filtered_ingresos_bar = [
        ingreso
        for ingreso in all_ingresos
        if selected_campaign is None
        or campaign_year(ingreso.fecha) == selected_campaign
    ]

    gastos_raw: dict = {0: defaultdict(float)}
    for gasto in filtered_gastos:
        gastos_raw[0][gasto.parcela_id] += gasto.cantidad

    distributed_gastos = distribute_unassigned_gastos(gastos_raw, all_parcelas)
    gas_per_parcela = distributed_gastos.get(0, {})

    ing_per_parcela: dict = defaultdict(float)
    for ingreso in filtered_ingresos_bar:
        if ingreso.parcela_id is not None:
            ing_per_parcela[ingreso.parcela_id] += ingreso.total

    parcela_labels = [parcela.nombre for parcela in all_parcelas]
    ing_values = [
        round(ing_per_parcela.get(parcela.id, 0.0), 2) for parcela in all_parcelas
    ]
    gas_values = [
        round(gas_per_parcela.get(parcela.id, 0.0), 2) for parcela in all_parcelas
    ]

    return {
        "all_campaigns": all_campaigns,
        "selected_campaign": selected_campaign,
        "all_parcelas": all_parcelas,
        "selected_bancal": selected_bancal,
        "kg_ha_table": kg_ha_table,
        "kg_ha_totals": kg_ha_totals,
        "week_labels": json.dumps(week_labels),
        "precio_semanal": json.dumps(precio_semanal),
        "kg_semanal": json.dumps(kg_semanal),
        "ingresos_acumulados": json.dumps(ingresos_acumulados),
        "cat_datasets": json.dumps(cat_datasets),
        "parcela_labels": json.dumps(parcela_labels),
        "ing_values": json.dumps(ing_values),
        "gas_values": json.dumps(gas_values),
    }

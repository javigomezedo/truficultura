from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Gasto, Ingreso, Parcela
from app.utils import campaign_year, distribute_unassigned_gastos


async def build_dashboard_context(db: AsyncSession) -> dict:
    parcelas_result = await db.execute(select(Parcela).order_by(Parcela.nombre))
    all_parcelas = parcelas_result.scalars().all()

    gastos_result = await db.execute(select(Gasto))
    all_gastos = gastos_result.scalars().all()

    ingresos_result = await db.execute(select(Ingreso))
    all_ingresos = ingresos_result.scalars().all()

    grand_gastos = sum(g.cantidad for g in all_gastos)
    grand_ingresos = sum(i.total for i in all_ingresos)
    grand_rentabilidad = grand_ingresos - grand_gastos

    gastos_raw: dict = defaultdict(lambda: defaultdict(float))
    for gasto in all_gastos:
        gastos_raw[campaign_year(gasto.fecha)][gasto.parcela_id] += gasto.cantidad

    gas_by_cy_p = distribute_unassigned_gastos(gastos_raw, all_parcelas)

    by_campaign: dict = defaultdict(lambda: {"gastos": 0.0, "ingresos": 0.0})
    for cy, by_parcela in gas_by_cy_p.items():
        by_campaign[cy]["gastos"] += sum(by_parcela.values())

    for ingreso in all_ingresos:
        by_campaign[campaign_year(ingreso.fecha)]["ingresos"] += ingreso.total

    campaigns = sorted(by_campaign.keys(), reverse=True)
    campaign_rows = [
        {
            "year": cy,
            "gastos": by_campaign[cy]["gastos"],
            "ingresos": by_campaign[cy]["ingresos"],
            "rentabilidad": by_campaign[cy]["ingresos"] - by_campaign[cy]["gastos"],
        }
        for cy in campaigns
    ]

    ing_by_cy_p: dict = defaultdict(lambda: defaultdict(float))
    for ingreso in all_ingresos:
        ing_by_cy_p[campaign_year(ingreso.fecha)][ingreso.parcela_id] += ingreso.total

    matrix = []
    parcela_totals: dict = defaultdict(
        lambda: {"ingresos": 0.0, "gastos": 0.0, "rentabilidad": 0.0}
    )
    for cy in campaigns:
        row = {"year": cy, "parcelas": {}}
        for parcela in all_parcelas:
            ing = ing_by_cy_p[cy][parcela.id]
            gas = gas_by_cy_p[cy][parcela.id]
            row["parcelas"][parcela.id] = {
                "ingresos": ing,
                "gastos": gas,
                "rentabilidad": ing - gas,
            }
            parcela_totals[parcela.id]["ingresos"] += ing
            parcela_totals[parcela.id]["gastos"] += gas

        row["total_ingresos"] = by_campaign[cy]["ingresos"]
        row["total_gastos"] = by_campaign[cy]["gastos"]
        row["total_rentabilidad"] = (
            by_campaign[cy]["ingresos"] - by_campaign[cy]["gastos"]
        )
        matrix.append(row)

    for pid in parcela_totals:
        parcela_totals[pid]["rentabilidad"] = (
            parcela_totals[pid]["ingresos"] - parcela_totals[pid]["gastos"]
        )

    return {
        "total_parcelas": len(all_parcelas),
        "grand_gastos": grand_gastos,
        "grand_ingresos": grand_ingresos,
        "grand_rentabilidad": grand_rentabilidad,
        "campaign_rows": campaign_rows,
        "parcelas": all_parcelas,
        "matrix": matrix,
        "parcela_totals": dict(parcela_totals),
    }

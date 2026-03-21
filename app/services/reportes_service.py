from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gasto import Gasto
from app.models.ingreso import Ingreso
from app.models.parcela import Parcela
from app.utils import campaign_year, distribute_unassigned_gastos


async def build_rentabilidad_context(db: AsyncSession) -> dict:
    parcelas_result = await db.execute(select(Parcela).order_by(Parcela.nombre))
    parcelas = parcelas_result.scalars().all()

    ingresos_result = await db.execute(select(Ingreso))
    ingresos = ingresos_result.scalars().all()

    gastos_result = await db.execute(select(Gasto))
    gastos = gastos_result.scalars().all()

    ingresos_by_year_parcela: dict = defaultdict(lambda: defaultdict(float))
    for ingreso in ingresos:
        cy = campaign_year(ingreso.fecha)
        ingresos_by_year_parcela[cy][ingreso.parcela_id] += ingreso.total

    gastos_raw: dict = defaultdict(lambda: defaultdict(float))
    for gasto in gastos:
        cy = campaign_year(gasto.fecha)
        gastos_raw[cy][gasto.parcela_id] += gasto.cantidad

    gastos_by_year_parcela = distribute_unassigned_gastos(gastos_raw, parcelas)

    all_years = sorted(
        set(
            list(ingresos_by_year_parcela.keys()) + list(gastos_by_year_parcela.keys())
        ),
        reverse=True,
    )

    parcela_ids = [parcela.id for parcela in parcelas]
    matrix = []
    year_totals = {}
    parcela_totals = defaultdict(
        lambda: {"ingresos": 0.0, "gastos": 0.0, "rentabilidad": 0.0}
    )

    for year in all_years:
        row = {"year": year, "parcelas": {}}
        year_ing = 0.0
        year_gasto = 0.0

        for pid in parcela_ids:
            ing = ingresos_by_year_parcela[year][pid]
            gasto = gastos_by_year_parcela[year][pid]
            rent = ing - gasto

            row["parcelas"][pid] = {
                "ingresos": ing,
                "gastos": gasto,
                "rentabilidad": rent,
            }

            year_ing += ing
            year_gasto += gasto
            parcela_totals[pid]["ingresos"] += ing
            parcela_totals[pid]["gastos"] += gasto
            parcela_totals[pid]["rentabilidad"] += rent

        row["total_ingresos"] = year_ing
        row["total_gastos"] = year_gasto
        row["total_rentabilidad"] = year_ing - year_gasto
        matrix.append(row)

        year_totals[year] = {
            "ingresos": year_ing,
            "gastos": year_gasto,
            "rentabilidad": year_ing - year_gasto,
        }

    for pid in parcela_ids:
        parcela_totals[pid]["rentabilidad"] = (
            parcela_totals[pid]["ingresos"] - parcela_totals[pid]["gastos"]
        )

    grand_total_ingresos = sum(yt["ingresos"] for yt in year_totals.values())
    grand_total_gastos = sum(yt["gastos"] for yt in year_totals.values())
    grand_total_rentabilidad = grand_total_ingresos - grand_total_gastos

    return {
        "parcelas": parcelas,
        "all_years": all_years,
        "matrix": matrix,
        "year_totals": year_totals,
        "parcela_totals": dict(parcela_totals),
        "grand_total_ingresos": grand_total_ingresos,
        "grand_total_gastos": grand_total_gastos,
        "grand_total_rentabilidad": grand_total_rentabilidad,
    }

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.gasto import Gasto
from app.models.parcela import Parcela
from app.utils import campaign_year, distribute_unassigned_gastos


async def list_parcelas(db: AsyncSession) -> list[Parcela]:
    result = await db.execute(select(Parcela).order_by(Parcela.nombre))
    return result.scalars().all()


async def get_gasto(db: AsyncSession, gasto_id: int) -> Optional[Gasto]:
    result = await db.execute(select(Gasto).where(Gasto.id == gasto_id))
    return result.scalar_one_or_none()


async def get_gastos_list_context(db: AsyncSession, year: Optional[int]) -> dict:
    result = await db.execute(select(Gasto).order_by(Gasto.fecha.desc()))
    all_gastos = result.scalars().all()

    parcelas_result = await db.execute(select(Parcela).order_by(Parcela.nombre))
    all_parcelas = parcelas_result.scalars().all()

    years = sorted(set(campaign_year(g.fecha) for g in all_gastos), reverse=True)
    gastos = (
        [g for g in all_gastos if campaign_year(g.fecha) == year]
        if year
        else all_gastos
    )

    total = sum(g.cantidad for g in gastos)
    current_year = year or (
        campaign_year(datetime.date.today())
        if all_gastos
        else datetime.date.today().year
    )

    # Breakdown table: direct gastos + distributed general gastos per parcela
    direct_by_p: dict = {p.id: 0.0 for p in all_parcelas}
    general_total = 0.0
    for g in gastos:
        if g.parcela_id is not None:
            direct_by_p[g.parcela_id] = direct_by_p.get(g.parcela_id, 0.0) + g.cantidad
        else:
            general_total += g.cantidad

    distributed = distribute_unassigned_gastos(
        {0: {p.id: direct_by_p[p.id] for p in all_parcelas} | {None: general_total}},
        all_parcelas,
    )
    distributed_by_p = distributed.get(0, {})

    breakdown = []
    for p in all_parcelas:
        directo = direct_by_p.get(p.id, 0.0)
        general_share = general_total * ((p.porcentaje or 0.0) / 100.0)
        breakdown.append(
            {
                "parcela": p,
                "directo": directo,
                "general_share": general_share,
                "total": directo + general_share,
            }
        )

    return {
        "gastos": gastos,
        "total": total,
        "years": years,
        "selected_year": year,
        "current_year": current_year,
        "breakdown": breakdown,
        "general_total": general_total,
    }


async def create_gasto(
    db: AsyncSession,
    *,
    fecha: datetime.date,
    concepto: str,
    persona: str,
    parcela_id: Optional[int],
    cantidad: float,
) -> Gasto:
    nuevo = Gasto(
        fecha=fecha,
        concepto=concepto,
        persona=persona,
        parcela_id=parcela_id if parcela_id else None,
        cantidad=cantidad,
    )
    db.add(nuevo)
    await db.flush()
    return nuevo


async def update_gasto(
    db: AsyncSession,
    gasto: Gasto,
    *,
    fecha: datetime.date,
    concepto: str,
    persona: str,
    parcela_id: Optional[int],
    cantidad: float,
) -> Gasto:
    gasto.fecha = fecha
    gasto.concepto = concepto
    gasto.persona = persona
    gasto.parcela_id = parcela_id if parcela_id else None
    gasto.cantidad = cantidad
    await db.flush()
    return gasto


async def delete_gasto(db: AsyncSession, gasto: Gasto) -> None:
    await db.delete(gasto)
    await db.flush()

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingreso import Ingreso
from app.models.parcela import Parcela
from app.utils import campaign_year


async def list_parcelas(db: AsyncSession) -> list[Parcela]:
    result = await db.execute(select(Parcela).order_by(Parcela.nombre))
    return result.scalars().all()


async def get_ingreso(db: AsyncSession, ingreso_id: int) -> Optional[Ingreso]:
    result = await db.execute(select(Ingreso).where(Ingreso.id == ingreso_id))
    return result.scalar_one_or_none()


async def get_ingresos_list_context(db: AsyncSession, year: Optional[int]) -> dict:
    result = await db.execute(
        select(Ingreso).order_by(Ingreso.fecha.desc(), Ingreso.categoria)
    )
    all_ingresos = result.scalars().all()

    years = sorted(set(campaign_year(i.fecha) for i in all_ingresos), reverse=True)
    ingresos = (
        [i for i in all_ingresos if campaign_year(i.fecha) == year]
        if year
        else all_ingresos
    )

    total_kg = sum(i.cantidad_kg for i in ingresos)
    total_euros = sum(i.total for i in ingresos)
    current_year = year or (
        campaign_year(datetime.date.today())
        if all_ingresos
        else datetime.date.today().year
    )

    return {
        "ingresos": ingresos,
        "total_kg": total_kg,
        "total_euros": total_euros,
        "years": years,
        "selected_year": year,
        "current_year": current_year,
    }


async def create_ingreso(
    db: AsyncSession,
    *,
    fecha: datetime.date,
    parcela_id: Optional[int],
    cantidad_kg: float,
    categoria: str,
    euros_kg: float,
) -> Ingreso:
    total = round(cantidad_kg * euros_kg, 2)
    nuevo = Ingreso(
        fecha=fecha,
        parcela_id=parcela_id if parcela_id else None,
        cantidad_kg=cantidad_kg,
        categoria=categoria,
        euros_kg=euros_kg,
        total=total,
    )
    db.add(nuevo)
    await db.flush()
    return nuevo


async def update_ingreso(
    db: AsyncSession,
    ingreso: Ingreso,
    *,
    fecha: datetime.date,
    parcela_id: Optional[int],
    cantidad_kg: float,
    categoria: str,
    euros_kg: float,
) -> Ingreso:
    total = round(cantidad_kg * euros_kg, 2)
    ingreso.fecha = fecha
    ingreso.parcela_id = parcela_id if parcela_id else None
    ingreso.cantidad_kg = cantidad_kg
    ingreso.categoria = categoria
    ingreso.euros_kg = euros_kg
    ingreso.total = total
    await db.flush()
    return ingreso


async def delete_ingreso(db: AsyncSession, ingreso: Ingreso) -> None:
    await db.delete(ingreso)
    await db.flush()

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.parcela import Parcela


async def list_parcelas(db: AsyncSession) -> list[Parcela]:
    result = await db.execute(select(Parcela).order_by(Parcela.nombre))
    return result.scalars().all()


async def get_parcela(db: AsyncSession, parcela_id: int) -> Optional[Parcela]:
    result = await db.execute(select(Parcela).where(Parcela.id == parcela_id))
    return result.scalar_one_or_none()


async def create_parcela(
    db: AsyncSession,
    *,
    nombre: str,
    poligono: str,
    parcela_catastro: str,
    hidrante: str,
    sector: str,
    n_carrascas: int,
    fecha_plantacion: datetime.date,
    superficie_ha: Optional[float],
    inicio_produccion: Optional[datetime.date],
    porcentaje: float,
) -> Parcela:
    nueva = Parcela(
        nombre=nombre,
        poligono=poligono,
        parcela=parcela_catastro,
        hidrante=hidrante,
        sector=sector,
        n_carrascas=n_carrascas,
        fecha_plantacion=fecha_plantacion,
        superficie_ha=superficie_ha,
        inicio_produccion=inicio_produccion,
        porcentaje=porcentaje,
    )
    db.add(nueva)
    await db.flush()
    return nueva


async def update_parcela(
    db: AsyncSession,
    parcela: Parcela,
    *,
    nombre: str,
    poligono: str,
    parcela_catastro: str,
    hidrante: str,
    sector: str,
    n_carrascas: int,
    fecha_plantacion: datetime.date,
    superficie_ha: Optional[float],
    inicio_produccion: Optional[datetime.date],
    porcentaje: float,
) -> Parcela:
    parcela.nombre = nombre
    parcela.poligono = poligono
    parcela.parcela = parcela_catastro
    parcela.hidrante = hidrante
    parcela.sector = sector
    parcela.n_carrascas = n_carrascas
    parcela.fecha_plantacion = fecha_plantacion
    parcela.superficie_ha = superficie_ha
    parcela.inicio_produccion = inicio_produccion
    parcela.porcentaje = porcentaje
    await db.flush()
    return parcela


async def delete_parcela(db: AsyncSession, parcela: Parcela) -> None:
    await db.delete(parcela)
    await db.flush()

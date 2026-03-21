from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.gasto import Gasto
    from app.models.ingreso import Ingreso


class Parcela(Base):
    __tablename__ = "parcelas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    poligono: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    parcela: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    hidrante: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    sector: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    n_carrascas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fecha_plantacion: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    superficie_ha: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    inicio_produccion: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    porcentaje: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Relationships
    gastos: Mapped[List["Gasto"]] = relationship(
        "Gasto", back_populates="parcela", lazy="select"
    )
    ingresos: Mapped[List["Ingreso"]] = relationship(
        "Ingreso", back_populates="parcela", lazy="select"
    )

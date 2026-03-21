from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.parcela import Parcela


class Gasto(Base):
    __tablename__ = "gastos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    concepto: Mapped[str] = mapped_column(String(500), nullable=False)
    persona: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    parcela_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("parcelas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cantidad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Relationship
    parcela: Mapped[Optional["Parcela"]] = relationship(
        "Parcela", back_populates="gastos", lazy="joined"
    )

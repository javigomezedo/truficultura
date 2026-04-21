from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plot import Plot
    from app.models.user import User


class RainfallRecord(Base):
    __tablename__ = "rainfall_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # nullable: registros de pluviómetro van ligados a parcela;
    # registros de AEMET/ibericam van a nivel de municipio (plot_id=NULL)
    plot_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("plots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Código INE del municipio (usado para registros AEMET/ibericam sin parcela concreta)
    municipio_cod: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, index=True
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    precipitation_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Fuente del dato: 'manual' | 'aemet' | 'ibericam'
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual", index=True
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_rainfall_user_date", "user_id", "date"),
        Index("ix_rainfall_user_plot_date", "user_id", "plot_id", "date"),
        Index("ix_rainfall_user_municipio_date", "user_id", "municipio_cod", "date"),
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="rainfall_records")
    plot: Mapped[Optional["Plot"]] = relationship(
        "Plot", back_populates="rainfall_records", lazy="joined"
    )

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.income import Income


class Plot(Base):
    __tablename__ = "plots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    polygon: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    cadastral_ref: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    hydrant: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    sector: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    num_holm_oaks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    planting_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    area_ha: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    production_start: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)
    percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Relationships
    expenses: Mapped[List["Expense"]] = relationship(
        "Expense", back_populates="plot", lazy="select"
    )
    incomes: Mapped[List["Income"]] = relationship(
        "Income", back_populates="plot", lazy="select"
    )

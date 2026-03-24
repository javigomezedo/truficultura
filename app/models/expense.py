from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plot import Plot
    from app.models.user import User

EXPENSE_CATEGORIES = [
    "Pozos",
    "Vallado",
    "Labrar",
    "Instalación riego",
    "Perros",
    "Riego",
    "Regadío Social",
    "Otros",
]


class Expense(Base):
    __tablename__ = "expenses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    person: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    plot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="expenses")
    plot: Mapped[Optional["Plot"]] = relationship(
        "Plot", back_populates="expenses", lazy="joined"
    )

from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plot import Plot
    from app.models.tenant import Tenant
    from app.models.user import User


class Income(Base):
    __tablename__ = "incomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    plot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    amount_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    category: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    euros_per_kg: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    @property
    def total(self) -> float:
        return round(self.amount_kg * self.euros_per_kg, 2)

    @total.setter
    def total(self, value: float) -> None:
        # Backward-compatible no-op: total is derived from amount_kg and euros_per_kg.
        return

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Income.created_by_user_id]"
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Income.updated_by_user_id]"
    )
    plot: Mapped[Optional["Plot"]] = relationship(
        "Plot", back_populates="incomes", lazy="joined"
    )

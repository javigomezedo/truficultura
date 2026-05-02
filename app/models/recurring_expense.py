from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plot import Plot
    from app.models.tenant import Tenant
    from app.models.user import User

# Valid frequency values and their Spanish labels
FREQUENCIES: dict[str, str] = {
    "weekly": "Semanal",
    "monthly": "Mensual",
    "annual": "Anual",
}


class RecurringExpense(Base):
    __tablename__ = "recurring_expenses"

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
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    plot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    person: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_date: Mapped[Optional[datetime.date]] = mapped_column(Date, nullable=True)

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[RecurringExpense.created_by_user_id]"
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[RecurringExpense.updated_by_user_id]"
    )
    plot: Mapped[Optional["Plot"]] = relationship(
        "Plot", back_populates="recurring_expenses", lazy="joined"
    )

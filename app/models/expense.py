from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Float, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.expense_proration_group import ExpenseProrationGroup
    from app.models.plot import Plot
    from app.models.tenant import Tenant
    from app.models.user import User

EXPENSE_CATEGORIES = [
    "Pozos",
    "Vallado",
    "Labrar",
    "Instalación riego",
    "Perros",
    "Plantel",
    "Riego",
    "Regadío Social",
    "Otros",
]


class Expense(Base):
    __tablename__ = "expenses"

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
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    person: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    plot_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="SET NULL"), nullable=True, index=True
    )
    amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    receipt_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    receipt_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    receipt_content_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )

    proration_group_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("expense_proration_groups.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Expense.created_by_user_id]"
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Expense.updated_by_user_id]"
    )
    plot: Mapped[Optional["Plot"]] = relationship(
        "Plot", back_populates="expenses", lazy="joined"
    )
    proration_group: Mapped[Optional["ExpenseProrationGroup"]] = relationship(
        "ExpenseProrationGroup", back_populates="expenses", lazy="joined"
    )

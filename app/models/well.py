from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.plot import Plot
    from app.models.plot_event import PlotEvent
    from app.models.tenant import Tenant
    from app.models.user import User


class Well(Base):
    __tablename__ = "wells"

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
    plot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    wells_per_plant: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expense_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("expenses.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Well.created_by_user_id]"
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Well.updated_by_user_id]"
    )
    plot: Mapped["Plot"] = relationship("Plot", back_populates="wells", lazy="joined")
    expense: Mapped[Optional["Expense"]] = relationship("Expense", lazy="joined")
    plot_events: Mapped[list["PlotEvent"]] = relationship(
        "PlotEvent", back_populates="related_well"
    )

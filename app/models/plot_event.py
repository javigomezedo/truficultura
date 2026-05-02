from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.irrigation import IrrigationRecord
    from app.models.plot import Plot
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.well import Well


class PlotEvent(Base):
    __tablename__ = "plot_events"

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
    event_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_recurring: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    related_irrigation_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("irrigation_records.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        unique=True,
    )
    related_well_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("wells.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        unique=True,
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    __table_args__ = (
        Index("ix_plot_event_tenant_plot_date", "tenant_id", "plot_id", "date"),
        Index("ix_plot_event_tenant_plot_type", "tenant_id", "plot_id", "event_type"),
    )

    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[PlotEvent.created_by_user_id]"
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[PlotEvent.updated_by_user_id]"
    )
    plot: Mapped["Plot"] = relationship("Plot", back_populates="plot_events")
    related_irrigation: Mapped[Optional["IrrigationRecord"]] = relationship(
        "IrrigationRecord", back_populates="plot_events", lazy="joined"
    )
    related_well: Mapped[Optional["Well"]] = relationship(
        "Well", back_populates="plot_events", lazy="joined"
    )

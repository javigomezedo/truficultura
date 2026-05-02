from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plant import Plant
    from app.models.plot import Plot
    from app.models.tenant import Tenant
    from app.models.user import User


class TruffleEvent(Base):
    __tablename__ = "truffle_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Denormalized for fast filtering without join
    plot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # "manual" | "qr"
    source: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    # Approximate harvested weight (grams) for this event
    estimated_weight_grams: Mapped[float] = mapped_column(
        Float, nullable=False, default=1.0
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Absolute deadline after which undo is no longer allowed (created_at + 30s)
    undo_window_expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Set when the event is reversed; NULL means the event is still active
    undone_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (
        Index("ix_truffle_event_tenant_plot_plant", "tenant_id", "plot_id", "plant_id"),
        Index("ix_truffle_event_plant_created", "plant_id", "created_at"),
    )

    # Relationships
    plant: Mapped["Plant"] = relationship("Plant", back_populates="truffle_events")
    plot: Mapped["Plot"] = relationship("Plot")
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[TruffleEvent.created_by_user_id]"
    )

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plot import Plot
    from app.models.tenant import Tenant
    from app.models.truffle_event import TruffleEvent
    from app.models.user import User


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    plot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    updated_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # Human-readable label, e.g. "A1", "B3", "AA12"
    label: Mapped[str] = mapped_column(String(20), nullable=False)
    # Row label part only, e.g. "A", "B", "AA" — used for grouping in the grid UI
    row_label: Mapped[str] = mapped_column(String(10), nullable=False)
    # 0-indexed stable positions for ordering and rendering
    row_order: Mapped[int] = mapped_column(Integer, nullable=False)
    col_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # 1-indexed visual column in the field layout (supports sparse rows and offsets)
    visual_col: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("plot_id", "label", name="uq_plant_label_per_plot"),
        UniqueConstraint(
            "plot_id", "row_order", "col_order", name="uq_plant_position_per_plot"
        ),
        Index("ix_plant_tenant_plot", "tenant_id", "plot_id"),
        Index("ix_plant_tenant_plot_visual", "tenant_id", "plot_id", "visual_col"),
    )

    # Relationships
    plot: Mapped["Plot"] = relationship("Plot", back_populates="plants")
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Plant.created_by_user_id]"
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Plant.updated_by_user_id]"
    )
    truffle_events: Mapped[List["TruffleEvent"]] = relationship(
        "TruffleEvent",
        back_populates="plant",
        lazy="select",
        cascade="all, delete-orphan",
    )

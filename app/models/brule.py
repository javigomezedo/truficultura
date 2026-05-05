from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plant import Plant
    from app.models.plot import Plot
    from app.models.tenant import Tenant
    from app.models.user import User


class BruleRecord(Base):
    __tablename__ = "brule_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    plot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    record_date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    diameter_cm: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("plant_id", "record_date", name="uq_brule_per_plant_per_day"),
        Index("ix_brule_tenant_plot", "tenant_id", "plot_id"),
        Index("ix_brule_tenant_plot_date", "tenant_id", "plot_id", "record_date"),
    )

    plant: Mapped["Plant"] = relationship("Plant")
    plot: Mapped["Plot"] = relationship("Plot")
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[BruleRecord.created_by_user_id]"
    )

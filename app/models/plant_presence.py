from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plant import Plant
    from app.models.plot import Plot
    from app.models.user import User


class PlantPresence(Base):
    __tablename__ = "plant_presences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    presence_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, index=True
    )
    has_truffle: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        UniqueConstraint("plant_id", "presence_date", name="uq_plant_presence_per_day"),
        Index("ix_plant_presence_user_plot", "user_id", "plot_id"),
        Index(
            "ix_plant_presence_user_plot_date", "user_id", "plot_id", "presence_date"
        ),
    )

    plant: Mapped["Plant"] = relationship("Plant")
    plot: Mapped["Plot"] = relationship("Plot", back_populates="plant_presences")
    user: Mapped["User"] = relationship("User")

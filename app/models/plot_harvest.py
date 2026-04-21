from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.plot import Plot
    from app.models.user import User


class PlotHarvest(Base):
    __tablename__ = "plot_harvests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    harvest_date: Mapped[datetime.date] = mapped_column(
        Date, nullable=False, index=True
    )
    weight_grams: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    __table_args__ = (
        Index("ix_plot_harvest_user_plot", "user_id", "plot_id"),
        Index("ix_plot_harvest_user_date", "user_id", "harvest_date"),
    )

    plot: Mapped["Plot"] = relationship("Plot", back_populates="plot_harvests")
    user: Mapped["User"] = relationship("User")

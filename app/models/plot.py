from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.income import Income
    from app.models.irrigation import IrrigationRecord
    from app.models.plant import Plant
    from app.models.plant_presence import PlantPresence
    from app.models.plot_event import PlotEvent
    from app.models.plot_harvest import PlotHarvest
    from app.models.rainfall import RainfallRecord
    from app.models.recurring_expense import RecurringExpense
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.well import Well


class Plot(Base):
    __tablename__ = "plots"

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
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    polygon: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    plot_num: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    cadastral_ref: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    hydrant: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    sector: Mapped[str] = mapped_column(String(100), nullable=False, default="")
    num_plants: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    planting_date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
    area_ha: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    production_start: Mapped[Optional[datetime.date]] = mapped_column(
        Date, nullable=True
    )
    percentage: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    has_irrigation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    recinto: Mapped[str] = mapped_column(String(10), nullable=False, default="1")
    caudal_riego: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    provincia_cod: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    municipio_cod: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    created_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Plot.created_by_user_id]"
    )
    updated_by: Mapped[Optional["User"]] = relationship(
        "User", foreign_keys="[Plot.updated_by_user_id]"
    )
    expenses: Mapped[List["Expense"]] = relationship(
        "Expense", back_populates="plot", lazy="select"
    )
    incomes: Mapped[List["Income"]] = relationship(
        "Income", back_populates="plot", lazy="select"
    )
    irrigation_records: Mapped[List["IrrigationRecord"]] = relationship(
        "IrrigationRecord", back_populates="plot", lazy="select"
    )
    wells: Mapped[List["Well"]] = relationship(
        "Well", back_populates="plot", lazy="select"
    )
    plot_events: Mapped[List["PlotEvent"]] = relationship(
        "PlotEvent", back_populates="plot", lazy="select", cascade="all, delete-orphan"
    )
    plants: Mapped[List["Plant"]] = relationship(
        "Plant", back_populates="plot", lazy="select", cascade="all, delete-orphan"
    )
    recurring_expenses: Mapped[List["RecurringExpense"]] = relationship(
        "RecurringExpense", back_populates="plot", lazy="select"
    )
    plot_harvests: Mapped[List["PlotHarvest"]] = relationship(
        "PlotHarvest",
        back_populates="plot",
        lazy="select",
        cascade="all, delete-orphan",
    )
    plant_presences: Mapped[List["PlantPresence"]] = relationship(
        "PlantPresence",
        back_populates="plot",
        lazy="select",
        cascade="all, delete-orphan",
    )
    rainfall_records: Mapped[List["RainfallRecord"]] = relationship(
        "RainfallRecord", back_populates="plot", lazy="select"
    )

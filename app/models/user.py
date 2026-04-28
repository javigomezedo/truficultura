from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.income import Income
    from app.models.irrigation import IrrigationRecord
    from app.models.plot import Plot
    from app.models.plot_event import PlotEvent
    from app.models.rainfall import RainfallRecord
    from app.models.recurring_expense import RecurringExpense
    from app.models.well import Well


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    email_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    comunidad_regantes: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Subscription / billing
    stripe_customer_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    subscription_status: Mapped[str] = mapped_column(
        String(30), default="trialing", server_default="trialing", nullable=False
    )
    trial_ends_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_ends_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    plots: Mapped[List["Plot"]] = relationship(
        "Plot", back_populates="user", lazy="select"
    )
    expenses: Mapped[List["Expense"]] = relationship(
        "Expense", back_populates="user", lazy="select"
    )
    incomes: Mapped[List["Income"]] = relationship(
        "Income", back_populates="user", lazy="select"
    )
    irrigation_records: Mapped[List["IrrigationRecord"]] = relationship(
        "IrrigationRecord", back_populates="user", lazy="select"
    )
    wells: Mapped[List["Well"]] = relationship(
        "Well", back_populates="user", lazy="select"
    )
    plot_events: Mapped[List["PlotEvent"]] = relationship(
        "PlotEvent", back_populates="user", lazy="select"
    )
    recurring_expenses: Mapped[List["RecurringExpense"]] = relationship(
        "RecurringExpense", back_populates="user", lazy="select"
    )
    rainfall_records: Mapped[List["RainfallRecord"]] = relationship(
        "RainfallRecord", back_populates="user", lazy="select"
    )

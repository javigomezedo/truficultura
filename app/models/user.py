from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.income import Income
    from app.models.plot import Plot


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
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

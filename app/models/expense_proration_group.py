from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.expense import Expense
    from app.models.user import User


class ExpenseProrationGroup(Base):
    """Metadata for a multi-year prorated expense.

    When a user prorates an expense over N years, one ExpenseProrationGroup is
    created to hold the original intent (total amount, number of years, start
    year) and N individual Expense records are created as children.

    Deleting this group cascades (at the DB level) to all child Expense rows.
    """

    __tablename__ = "expense_proration_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    total_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    years: Mapped[int] = mapped_column(Integer, nullable=False)
    start_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Relationships
    user: Mapped["User"] = relationship("User")
    expenses: Mapped[list["Expense"]] = relationship(
        "Expense",
        back_populates="proration_group",
        passive_deletes=True,
    )

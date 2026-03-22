import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ExpenseBase(BaseModel):
    date: datetime.date
    description: str
    person: str = ""
    plot_id: Optional[int] = None
    amount: float = 0.0
    category: Optional[str] = None


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    date: Optional[datetime.date] = None
    description: Optional[str] = None
    person: Optional[str] = None
    plot_id: Optional[int] = None
    amount: Optional[float] = None
    category: Optional[str] = None


class ExpenseResponse(ExpenseBase):
    id: int
    plot_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_plot(cls, expense) -> "ExpenseResponse":
        return cls(
            id=expense.id,
            date=expense.date,
            description=expense.description,
            person=expense.person,
            plot_id=expense.plot_id,
            amount=expense.amount,
            plot_name=expense.plot.name if expense.plot else None,
        )

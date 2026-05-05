import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ExpenseBase(BaseModel):
    date: datetime.date
    description: str = Field(..., max_length=500)
    person: str = Field("", max_length=200)
    plot_id: Optional[int] = None
    amount: float = 0.0
    category: Optional[str] = Field(None, max_length=100)


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    date: Optional[datetime.date] = None
    description: Optional[str] = Field(None, max_length=500)
    person: Optional[str] = Field(None, max_length=200)
    plot_id: Optional[int] = None
    amount: Optional[float] = None
    category: Optional[str] = Field(None, max_length=100)


class ExpenseResponse(ExpenseBase):
    id: int
    plot_name: Optional[str] = None
    receipt_filename: Optional[str] = None

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

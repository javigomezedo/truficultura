import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class IncomeBase(BaseModel):
    date: datetime.date
    plot_id: Optional[int] = None
    amount_kg: float = 0.0
    category: str = ""
    euros_per_kg: float = 0.0
    total: float = 0.0


class IncomeCreate(IncomeBase):
    pass


class IncomeUpdate(BaseModel):
    date: Optional[datetime.date] = None
    plot_id: Optional[int] = None
    amount_kg: Optional[float] = None
    category: Optional[str] = None
    euros_per_kg: Optional[float] = None
    total: Optional[float] = None


class IncomeResponse(IncomeBase):
    id: int
    plot_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_plot(cls, income) -> "IncomeResponse":
        return cls(
            id=income.id,
            date=income.date,
            plot_id=income.plot_id,
            amount_kg=income.amount_kg,
            category=income.category,
            euros_per_kg=income.euros_per_kg,
            total=income.total,
            plot_name=income.plot.name if income.plot else None,
        )

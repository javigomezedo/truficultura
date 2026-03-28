import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field


class IrrigationBase(BaseModel):
    plot_id: int
    date: datetime.date
    water_m3: float
    expense_id: Optional[int] = None
    notes: Optional[str] = None


class IrrigationCreate(IrrigationBase):
    pass


class IrrigationUpdate(BaseModel):
    plot_id: Optional[int] = None
    date: Optional[datetime.date] = None
    water_m3: Optional[float] = None
    expense_id: Optional[int] = None
    notes: Optional[str] = None


class IrrigationResponse(IrrigationBase):
    id: int
    user_id: Optional[int] = None
    plot_name: Optional[str] = None
    expense_description: Optional[str] = None
    expense_amount: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def water_liters(self) -> float:
        return round(self.water_m3 * 1000, 1)

import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, computed_field


class WellBase(BaseModel):
    plot_id: int
    date: datetime.date
    wells_per_plant: int
    expense_id: Optional[int] = None
    notes: Optional[str] = None


class WellCreate(WellBase):
    pass


class WellUpdate(BaseModel):
    plot_id: Optional[int] = None
    date: Optional[datetime.date] = None
    wells_per_plant: Optional[int] = None
    expense_id: Optional[int] = None
    notes: Optional[str] = None


class WellResponse(WellBase):
    id: int
    user_id: Optional[int] = None
    plot_name: Optional[str] = None
    expense_description: Optional[str] = None
    expense_amount: Optional[float] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def total_wells(self) -> int:
        plot = getattr(self, "plot", None)
        return self.wells_per_plant * (
            plot.num_plants
            if plot is not None and getattr(plot, "num_plants", 0)
            else 0
        )

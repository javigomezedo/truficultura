import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlotBase(BaseModel):
    name: str
    polygon: str = ""
    plot_num: str = ""
    cadastral_ref: str = ""
    hydrant: str = ""
    sector: str = ""
    num_plants: int = 0
    planting_date: datetime.date
    area_ha: Optional[float] = None
    production_start: Optional[datetime.date] = None
    percentage: float = 0.0


class PlotCreate(PlotBase):
    pass


class PlotUpdate(BaseModel):
    name: Optional[str] = None
    polygon: Optional[str] = None
    plot_num: Optional[str] = None
    cadastral_ref: Optional[str] = None
    hydrant: Optional[str] = None
    sector: Optional[str] = None
    num_plants: Optional[int] = None
    planting_date: Optional[datetime.date] = None
    area_ha: Optional[float] = None
    production_start: Optional[datetime.date] = None
    percentage: Optional[float] = None


class PlotResponse(PlotBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

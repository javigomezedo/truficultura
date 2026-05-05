import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class PlotBase(BaseModel):
    name: str = Field(..., max_length=200)
    polygon: str = Field("", max_length=100)
    plot_num: str = Field("", max_length=50)
    cadastral_ref: str = Field("", max_length=100)
    hydrant: str = Field("", max_length=100)
    sector: str = Field("", max_length=100)
    num_plants: int = 0
    planting_date: datetime.date
    area_ha: Optional[float] = None
    production_start: Optional[datetime.date] = None
    percentage: float = 0.0
    has_irrigation: bool = False
    recinto: str = Field("1", max_length=20)
    caudal_riego: Optional[float] = None
    provincia_cod: Optional[str] = Field(None, max_length=10)
    municipio_cod: Optional[str] = Field(None, max_length=10)


class PlotCreate(PlotBase):
    pass


class PlotUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    polygon: Optional[str] = Field(None, max_length=100)
    plot_num: Optional[str] = Field(None, max_length=50)
    cadastral_ref: Optional[str] = Field(None, max_length=100)
    hydrant: Optional[str] = Field(None, max_length=100)
    sector: Optional[str] = Field(None, max_length=100)
    num_plants: Optional[int] = None
    planting_date: Optional[datetime.date] = None
    area_ha: Optional[float] = None
    production_start: Optional[datetime.date] = None
    percentage: Optional[float] = None
    has_irrigation: Optional[bool] = None
    recinto: Optional[str] = Field(None, max_length=20)
    caudal_riego: Optional[float] = None
    provincia_cod: Optional[str] = Field(None, max_length=10)
    municipio_cod: Optional[str] = Field(None, max_length=10)


class PlotResponse(PlotBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

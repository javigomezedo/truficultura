import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, model_validator


RainfallSource = Literal["manual", "aemet", "ibericam"]


class RainfallBase(BaseModel):
    plot_id: Optional[int] = None
    municipio_cod: Optional[str] = None
    date: datetime.date
    precipitation_mm: float
    source: RainfallSource = "manual"
    notes: Optional[str] = None

    @model_validator(mode="after")
    def require_plot_or_municipio(self) -> "RainfallBase":
        if self.plot_id is None and not self.municipio_cod:
            raise ValueError(
                "Se debe especificar una parcela (plot_id) o un municipio (municipio_cod)"
            )
        return self


class RainfallCreate(RainfallBase):
    pass


class RainfallUpdate(BaseModel):
    plot_id: Optional[int] = None
    municipio_cod: Optional[str] = None
    date: Optional[datetime.date] = None
    precipitation_mm: Optional[float] = None
    source: Optional[RainfallSource] = None
    notes: Optional[str] = None


class RainfallResponse(RainfallBase):
    id: int
    user_id: Optional[int]
    plot_name: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

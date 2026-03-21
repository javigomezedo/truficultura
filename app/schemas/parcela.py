import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ParcelaBase(BaseModel):
    nombre: str
    poligono: str = ""
    parcela: str = ""
    hidrante: str = ""
    sector: str = ""
    n_carrascas: int = 0
    fecha_plantacion: datetime.date
    superficie_ha: Optional[float] = None
    inicio_produccion: Optional[datetime.date] = None
    porcentaje: float = 0.0


class ParcelaCreate(ParcelaBase):
    pass


class ParcelaUpdate(BaseModel):
    nombre: Optional[str] = None
    poligono: Optional[str] = None
    parcela: Optional[str] = None
    hidrante: Optional[str] = None
    sector: Optional[str] = None
    n_carrascas: Optional[int] = None
    fecha_plantacion: Optional[datetime.date] = None
    superficie_ha: Optional[float] = None
    inicio_produccion: Optional[datetime.date] = None
    porcentaje: Optional[float] = None


class ParcelaResponse(ParcelaBase):
    id: int

    model_config = ConfigDict(from_attributes=True)

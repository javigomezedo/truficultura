import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class IngresoBase(BaseModel):
    fecha: datetime.date
    parcela_id: Optional[int] = None
    cantidad_kg: float = 0.0
    categoria: str = ""
    euros_kg: float = 0.0
    total: float = 0.0


class IngresoCreate(IngresoBase):
    pass


class IngresoUpdate(BaseModel):
    fecha: Optional[datetime.date] = None
    parcela_id: Optional[int] = None
    cantidad_kg: Optional[float] = None
    categoria: Optional[str] = None
    euros_kg: Optional[float] = None
    total: Optional[float] = None


class IngresoResponse(IngresoBase):
    id: int
    parcela_nombre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_parcela(cls, ingreso) -> "IngresoResponse":
        return cls(
            id=ingreso.id,
            fecha=ingreso.fecha,
            parcela_id=ingreso.parcela_id,
            cantidad_kg=ingreso.cantidad_kg,
            categoria=ingreso.categoria,
            euros_kg=ingreso.euros_kg,
            total=ingreso.total,
            parcela_nombre=ingreso.parcela.nombre if ingreso.parcela else None,
        )

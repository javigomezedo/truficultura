import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class GastoBase(BaseModel):
    fecha: datetime.date
    concepto: str
    persona: str = ""
    parcela_id: Optional[int] = None
    cantidad: float = 0.0


class GastoCreate(GastoBase):
    pass


class GastoUpdate(BaseModel):
    fecha: Optional[datetime.date] = None
    concepto: Optional[str] = None
    persona: Optional[str] = None
    parcela_id: Optional[int] = None
    cantidad: Optional[float] = None


class GastoResponse(GastoBase):
    id: int
    parcela_nombre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_with_parcela(cls, gasto) -> "GastoResponse":
        return cls(
            id=gasto.id,
            fecha=gasto.fecha,
            concepto=gasto.concepto,
            persona=gasto.persona,
            parcela_id=gasto.parcela_id,
            cantidad=gasto.cantidad,
            parcela_nombre=gasto.parcela.nombre if gasto.parcela else None,
        )

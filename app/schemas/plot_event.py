from __future__ import annotations

import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict


class EventType(str, Enum):
    LABRADO = "labrado"
    PICADO = "picado"
    PODA = "poda"
    VALLADO = "vallado"
    INSTALLED_DRIP = "installed_drip"
    RIEGO = "riego"
    POZO = "pozo"


class PlotEventBase(BaseModel):
    plot_id: int
    event_type: EventType
    date: datetime.date
    notes: Optional[str] = None
    is_recurring: Optional[bool] = None


class PlotEventCreate(PlotEventBase):
    pass


class PlotEventUpdate(BaseModel):
    event_type: Optional[EventType] = None
    date: Optional[datetime.date] = None
    notes: Optional[str] = None
    is_recurring: Optional[bool] = None


class PlotEventResponse(BaseModel):
    id: int
    user_id: int
    plot_id: int
    event_type: EventType
    date: datetime.date
    notes: Optional[str] = None
    is_recurring: bool
    related_irrigation_id: Optional[int] = None
    related_well_id: Optional[int] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class WeatherDailyRecord(Base):
    __tablename__ = "weather_daily_records"
    __table_args__ = (
        UniqueConstraint(
            "date",
            "station_code",
            "province_code",
            "municipality_code",
            "is_forecast",
            name="uq_weather_daily_scope",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    date: Mapped[datetime.date] = mapped_column(Date, nullable=False, index=True)
    station_code: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, index=True
    )
    province_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, index=True
    )
    municipality_code: Mapped[Optional[str]] = mapped_column(
        String(10), nullable=True, index=True
    )
    precipitation_mm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_forecast: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    quality_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ok"
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="aemet_api")
    fetched_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.datetime.utcnow
    )

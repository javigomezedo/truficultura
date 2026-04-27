from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class LeadCapture(Base):
    __tablename__ = "lead_captures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Hash parcial SHA-256 de la IP (RGPD: no se guarda la IP en claro)
    ip_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Mensaje libre del usuario (motivo de la consulta)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Gestión de contacto
    contacted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    contacted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

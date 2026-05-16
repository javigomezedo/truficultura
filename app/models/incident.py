from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.tenant import Tenant
    from app.models.user import User


INCIDENT_CATEGORIES = [
    "error_visual",
    "error_texto",
    "boton_roto",
    "error_sistema",
    "otro",
]

INCIDENT_CATEGORY_LABELS = {
    "error_visual": "Error visual",
    "error_texto": "Texto incorrecto",
    "boton_roto": "Botón roto",
    "error_sistema": "Error del sistema",
    "otro": "Otro",
}

INCIDENT_SEVERITIES = ["baja", "media", "alta", "critica"]

INCIDENT_SEVERITY_LABELS = {
    "baja": "Baja",
    "media": "Media",
    "alta": "Alta",
    "critica": "Crítica",
}


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False, default="otro")
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="media")

    # Adjunto almacenado en BD (igual que receipts en Expense)
    attachment_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    attachment_data: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    attachment_content_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    admin_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    resolved_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    tenant: Mapped[Optional["Tenant"]] = relationship("Tenant")
    user: Mapped[Optional["User"]] = relationship("User", foreign_keys="[Incident.user_id]")

    @property
    def category_label(self) -> str:
        return INCIDENT_CATEGORY_LABELS.get(self.category, self.category)

    @property
    def severity_label(self) -> str:
        return INCIDENT_SEVERITY_LABELS.get(self.severity, self.severity)

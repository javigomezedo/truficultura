from __future__ import annotations

import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

# Status values for an onboarding session lifecycle.
ONBOARDING_STATUSES = (
    "uploaded",       # File received, parsing pending
    "mapping",        # LLM is detecting entity / mapping columns
    "awaiting_user",  # Waiting for user to resolve ambiguities
    "transforming",   # Local transformation + validation in progress
    "previewing",     # Preview ready, awaiting confirmation
    "imported",       # Successfully imported into the system
    "cancelled",      # User cancelled
    "error",          # Unrecoverable error (LLM failure, parse failure)
)

# Entity types supported by the onboarding agent (MVP).
ONBOARDING_ENTITY_TYPES = ("parcelas", "gastos", "ingresos", "desconocido")


class OnboardingSession(Base):
    """A historical-data onboarding session orchestrated by the LLM agent.

    Each session represents one Excel file uploaded by a user that needs to be
    mapped to a Trufiq entity (parcelas/gastos/ingresos) and imported via
    ``app.services.import_service``.

    The full agent state (headers, sample rows, proposed mapping, ambiguities,
    transformed rows, validation errors, generated CSV...) is serialised in
    ``state_json`` between HTTP requests so the LangGraph workflow can resume.
    """

    __tablename__ = "onboarding_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="uploaded")
    entity_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    # SQLAlchemy JSONB on PostgreSQL; on SQLite (tests) falls back to TEXT-JSON
    # via the dialect's native type emulation.
    state_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Original uploaded Excel bytes — needed during the transform phase to
    # re-read the full file (the JSON state only stores a small sample).
    raw_file: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_onboarding_tenant_status", "tenant_id", "status"),
        Index(
            "ix_onboarding_sessions_tenant_id_created_at",
            "tenant_id",
            "created_at",
        ),
    )

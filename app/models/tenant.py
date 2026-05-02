from __future__ import annotations

import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from app.models.user import User


class Tenant(Base):
    """Nivel de empresa / tenant. Los datos de la aplicación se asocian a este nivel."""

    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(
        String(100), unique=True, nullable=False, index=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Billing — movido desde User
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, unique=True, index=True
    )
    subscription_status: Mapped[str] = mapped_column(
        String(30), default="trialing", server_default="trialing", nullable=False
    )
    trial_ends_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    subscription_ends_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    memberships: Mapped[List["TenantMembership"]] = relationship(
        "TenantMembership",
        back_populates="tenant",
        lazy="select",
        cascade="all, delete-orphan",
    )
    invitations: Mapped[List["TenantInvitation"]] = relationship(
        "TenantInvitation",
        back_populates="tenant",
        lazy="select",
        cascade="all, delete-orphan",
    )


class TenantMembership(Base):
    """Asociación entre un User y un Tenant, con rol dentro del tenant."""

    __tablename__ = "tenant_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "owner" | "admin" | "member"
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    joined_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    invited_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
        Index("ix_tenant_membership_user", "user_id"),
        Index("ix_tenant_membership_tenant", "tenant_id"),
    )

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="memberships")
    user: Mapped["User"] = relationship(
        "User",
        back_populates="membership",
        foreign_keys="[TenantMembership.user_id]",
    )
    invited_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys="[TenantMembership.invited_by_user_id]",
    )


class TenantInvitation(Base):
    """Invitación por email para unirse a un tenant."""

    __tablename__ = "tenant_invitations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Token URL-safe de 32 bytes (64 hex chars)
    token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    invited_by_user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Rol que tendrá el invitado al aceptar
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    accepted_at: Mapped[Optional[datetime.datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    __table_args__ = (Index("ix_tenant_invitation_tenant", "tenant_id"),)

    tenant: Mapped["Tenant"] = relationship("Tenant", back_populates="invitations")
    invited_by: Mapped["User"] = relationship(
        "User",
        foreign_keys="[TenantInvitation.invited_by_user_id]",
    )

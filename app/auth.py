from __future__ import annotations

from datetime import UTC, datetime
from typing import Optional

from fastapi import Depends, Request
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.tenant import Tenant, TenantMembership
from app.models.user import User

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

_TRANSIENT_DB_ERROR_MARKERS = (
    "connectiondoesnotexisterror",
    "connection was closed in the middle of operation",
    "server closed the connection",
    "connection reset by peer",
    "terminating connection",
)


def _is_transient_db_connection_error(exc: Exception) -> bool:
    current: Exception | None = exc
    while current is not None:
        text = f"{type(current).__name__}: {current}".lower()
        if any(marker in text for marker in _TRANSIENT_DB_ERROR_MARKERS):
            return True
        next_exc = current.__cause__ or current.__context__
        current = next_exc if isinstance(next_exc, Exception) else None
    return False


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None

    user: Optional[User] = None
    for attempt in range(2):
        try:
            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            break
        except Exception as exc:
            if not _is_transient_db_connection_error(exc):
                raise

            if attempt == 0:
                # Retry once with a clean transaction state for transient pool/socket cuts.
                await db.rollback()
                continue

            # If the connection keeps failing, degrade to unauthenticated
            # so middleware returns a login redirect instead of 500.
            request.session.clear()
            return None

    # If user doesn't exist in database but session has user_id, clear the session
    # This prevents redirect loops when database is cleaned
    if user is None and user_id is not None:
        request.session.clear()
        return None

    # Load the tenant membership for this user
    if user is not None:
        membership_result = await db.execute(
            select(TenantMembership)
            .where(TenantMembership.user_id == user.id)
        )
        membership = membership_result.scalar_one_or_none()

        if membership is not None:
            tenant_result = await db.execute(
                select(Tenant).where(Tenant.id == membership.tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
        else:
            tenant = None

        # Attach tenant info as dynamic attributes on the user object
        user.active_tenant_id = membership.tenant_id if membership else None  # type: ignore[attr-defined]
        user.tenant_role = membership.role if membership else None  # type: ignore[attr-defined]
        user.active_tenant = tenant  # type: ignore[attr-defined]

        # Refresh subscription data in session so base.html can read it without
        # needing current_user in every router's template context.
        sub_status = tenant.subscription_status if tenant else "trialing"
        trial_ends_at = tenant.trial_ends_at if tenant else None
        subscription_ends_at = tenant.subscription_ends_at if tenant else None

        request.session["subscription_status"] = sub_status
        if trial_ends_at:
            delta = trial_ends_at - datetime.now(UTC)
            request.session["trial_days_left"] = delta.days
        else:
            request.session["trial_days_left"] = None
        if subscription_ends_at:
            delta = subscription_ends_at - datetime.now(UTC)
            request.session["subscription_days_left"] = delta.days
        else:
            request.session["subscription_days_left"] = None

    return user


class NotAuthenticatedException(Exception):
    """Raised by require_user when no valid session exists."""


class NotAdminException(Exception):
    """Raised by require_admin when user is not an admin."""


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_current_user(request, db)
    if user is None or user.role != "admin":
        raise NotAdminException()
    return user


async def require_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await get_current_user(request, db)
    if user is None:
        raise NotAuthenticatedException()
    return user


class SubscriptionRequiredException(Exception):
    """Raised when a user's trial has expired and they have no active subscription."""


def is_subscription_blocked(user: User) -> bool:
    """Return True if the user's tenant should be blocked from accessing the app."""
    if user.role == "admin":
        return False
    tenant: Optional[Tenant] = getattr(user, "active_tenant", None)
    if tenant is None:
        # No tenant yet (rare during registration flow) — allow access
        return False
    now = datetime.now(UTC)
    status = tenant.subscription_status
    if status == "trialing":
        return not (tenant.trial_ends_at and tenant.trial_ends_at > now)
    if status == "active":
        return (
            tenant.subscription_ends_at is not None and tenant.subscription_ends_at <= now
        )
    return True


async def require_subscription(
    user: User = Depends(require_user),
) -> User:
    """Verify the user has an active trial or paid subscription.

    Admin users are always exempt.
    Allowed subscription_status values:
    - "trialing" with trial_ends_at > now
    - "active" with subscription_ends_at > now (or no expiry set)
    - "active" regardless (belt-and-suspenders for freshly activated users)
    """
    if user.role == "admin":
        return user

    if is_subscription_blocked(user):
        raise SubscriptionRequiredException()
    return user

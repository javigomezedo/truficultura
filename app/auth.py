from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

    # Update last_seen_at throttled: write at most once per hour to avoid
    # excess DB writes on every request.
    if user is not None:
        now = datetime.now(UTC)
        if user.last_seen_at is None or (now - user.last_seen_at) >= timedelta(hours=1):
            user.last_seen_at = now
            try:
                await db.commit()
            except Exception:
                await db.rollback()

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
        request.session["tenant_plan"] = tenant.plan if tenant else None
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
    """Kept for backward compatibility. Always returns False in the new plan system.

    Expired trials and past_due/canceled tenants now get read-only access instead
    of a hard block. Use plan_access.is_read_only() or plan_access.require_write_access
    for write-gating.
    """
    return False


async def require_subscription(
    user: User = Depends(require_user),
) -> User:
    """Verify the user is authenticated and has an active tenant.

    In the new plan system all authenticated users are allowed to access the app
    (expired trials become read-only). Feature/write gating is enforced by the
    plan_access module. Admin users are always granted full access.
    """
    return user

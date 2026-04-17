from __future__ import annotations

from typing import Optional

from fastapi import Depends, Request
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
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

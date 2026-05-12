from __future__ import annotations

from typing import Union

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_id(db: AsyncSession, user_id: int) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


async def update_profile(
    db: AsyncSession,
    user: User,
    first_name: str,
    last_name: str,
    username: str,
    comunidad_regantes: bool,
) -> Union[User, str]:
    """Update profile fields. Returns the updated User on success or an error message string."""
    username = username.strip()
    first_name = first_name.strip()
    last_name = last_name.strip()

    if username != user.username:
        result = await db.execute(select(User).where(User.username == username))
        existing = result.scalar_one_or_none()
        if existing is not None:
            return "El nombre de usuario ya está en uso."

    user.first_name = first_name
    user.last_name = last_name
    user.username = username
    user.comunidad_regantes = comunidad_regantes
    await db.commit()
    return user

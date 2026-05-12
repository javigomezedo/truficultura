from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import User
from app.services.profile_service import get_user_by_id, update_profile
from tests.conftest import result


def _user(**kwargs) -> User:
    defaults = dict(
        id=1,
        username="trufero",
        first_name="Juan",
        last_name="García",
        email="juan@example.com",
        hashed_password="x",
        role="user",
        is_active=True,
        email_confirmed=True,
        comunidad_regantes=False,
    )
    defaults.update(kwargs)
    return User(**defaults)


@pytest.mark.asyncio
async def test_get_user_by_id_found() -> None:
    user = _user()
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([user]))

    found = await get_user_by_id(db, user_id=1)

    assert found is user


@pytest.mark.asyncio
async def test_get_user_by_id_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_user_by_id(db, user_id=99)

    assert found is None


@pytest.mark.asyncio
async def test_update_profile_success() -> None:
    user = _user()
    db = MagicMock()
    # No duplicate username found
    db.execute = AsyncMock(return_value=result([]))
    db.commit = AsyncMock()

    result_val = await update_profile(
        db=db,
        user=user,
        first_name="  Pedro  ",
        last_name="López",
        username="new_trufero",
        comunidad_regantes=True,
    )

    assert result_val is user
    assert user.first_name == "Pedro"
    assert user.last_name == "López"
    assert user.username == "new_trufero"
    assert user.comunidad_regantes is True
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_profile_same_username_no_uniqueness_check() -> None:
    """When username is unchanged, no DB uniqueness query is made."""
    user = _user(username="trufero")
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.commit = AsyncMock()

    result_val = await update_profile(
        db=db,
        user=user,
        first_name="Juan",
        last_name="García",
        username="trufero",
        comunidad_regantes=False,
    )

    assert result_val is user
    # execute should NOT have been called for uniqueness check since username didn't change
    db.execute.assert_not_awaited()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_profile_duplicate_username_returns_error() -> None:
    user = _user(username="trufero")
    other = _user(id=2, username="nuevo")
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([other]))
    db.commit = AsyncMock()

    result_val = await update_profile(
        db=db,
        user=user,
        first_name="Juan",
        last_name="García",
        username="nuevo",
        comunidad_regantes=False,
    )

    assert isinstance(result_val, str)
    assert "usuario" in result_val.lower()
    db.commit.assert_not_awaited()

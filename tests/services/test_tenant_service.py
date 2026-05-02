from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from tests.conftest import result

from app.models.tenant import Tenant, TenantMembership
from app.models.user import User
from app.services import tenant_service


def _make_tenant(**kwargs) -> Tenant:
    t = Tenant()
    t.id = kwargs.get("id", 1)
    t.name = kwargs.get("name", "Finca Demo")
    t.slug = kwargs.get("slug", "finca-demo")
    return t


def _make_membership(role: str = "owner", user_id: int = 1) -> TenantMembership:
    m = TenantMembership()
    m.id = 1
    m.tenant_id = 1
    m.user_id = user_id
    m.role = role
    m.joined_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
    return m


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


# ── get_tenant ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_tenant_found() -> None:
    tenant = _make_tenant()
    db = _fake_db()
    db.execute.return_value = result([tenant])

    found = await tenant_service.get_tenant(db, 1)
    assert found is tenant


@pytest.mark.asyncio
async def test_get_tenant_not_found() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    found = await tenant_service.get_tenant(db, 99)
    assert found is None


# ── update_tenant ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_tenant_changes_name() -> None:
    tenant = _make_tenant(name="Viejo Nombre")
    db = _fake_db()
    db.execute.return_value = result([tenant])

    updated = await tenant_service.update_tenant(
        db, tenant_id=1, name="  Nuevo Nombre  "
    )

    assert updated.name == "Nuevo Nombre"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_tenant_not_found_raises_404() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    with pytest.raises(HTTPException) as exc:
        await tenant_service.update_tenant(db, tenant_id=99, name="X")

    assert exc.value.status_code == 404


# ── list_members ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_members_returns_memberships() -> None:
    m1 = _make_membership(role="owner")
    m2 = _make_membership(role="member", user_id=2)
    db = _fake_db()
    db.execute.return_value = result([m1, m2])

    members = await tenant_service.list_members(db, tenant_id=1)

    assert len(members) == 2
    assert members[0] is m1


# ── get_membership ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_membership_found() -> None:
    m = _make_membership()
    db = _fake_db()
    db.execute.return_value = result([m])

    found = await tenant_service.get_membership(db, tenant_id=1, user_id=1)
    assert found is m


@pytest.mark.asyncio
async def test_get_membership_not_found() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    found = await tenant_service.get_membership(db, tenant_id=1, user_id=99)
    assert found is None


# ── change_member_role ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_change_member_role_success() -> None:
    m = _make_membership(role="member")
    db = _fake_db()
    db.execute.return_value = result([m])

    updated = await tenant_service.change_member_role(
        db, tenant_id=1, user_id=1, new_role="admin"
    )

    assert updated.role == "admin"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_change_member_role_owner_raises_400() -> None:
    m = _make_membership(role="owner")
    db = _fake_db()
    db.execute.return_value = result([m])

    with pytest.raises(HTTPException) as exc:
        await tenant_service.change_member_role(
            db, tenant_id=1, user_id=1, new_role="member"
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_change_member_role_invalid_role_raises_400() -> None:
    m = _make_membership(role="member")
    db = _fake_db()
    db.execute.return_value = result([m])

    with pytest.raises(HTTPException) as exc:
        await tenant_service.change_member_role(
            db, tenant_id=1, user_id=1, new_role="superadmin"
        )

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_change_member_role_not_found_raises_404() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    with pytest.raises(HTTPException) as exc:
        await tenant_service.change_member_role(
            db, tenant_id=1, user_id=99, new_role="admin"
        )

    assert exc.value.status_code == 404


# ── remove_member ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_remove_member_success() -> None:
    """Al expulsar a un miembro se crea un nuevo solo-tenant para él."""
    m = _make_membership(role="member", user_id=2)
    user = User()
    user.id = 2
    user.first_name = "Ana"
    user.last_name = "López"
    user.username = "ana"

    db = _fake_db()
    # 1st execute: get_membership → m
    # 2nd execute: get User for solo-tenant creation → user
    # 3rd execute: slug uniqueness check → empty
    from tests.conftest import result as _result

    db.execute.side_effect = [_result([m]), _result([user]), _result([])]

    await tenant_service.remove_member(db, tenant_id=1, user_id=2)

    db.delete.assert_awaited_once_with(m)
    assert (
        db.flush.await_count == 3
    )  # delete + flush new Tenant + flush new TenantMembership
    assert db.add.call_count == 2  # new Tenant + new TenantMembership


@pytest.mark.asyncio
async def test_remove_member_creates_solo_tenant() -> None:
    """El solo-tenant creado vincula al usuario expulsado como owner."""
    m = _make_membership(role="admin", user_id=3)
    user = User()
    user.id = 3
    user.first_name = "Pedro"
    user.last_name = "García"
    user.username = "pedro"

    db = _fake_db()
    from tests.conftest import result as _result

    db.execute.side_effect = [_result([m]), _result([user]), _result([])]

    await tenant_service.remove_member(db, tenant_id=1, user_id=3)

    # Second db.add call is the TenantMembership (solo-tenant membership)
    added_membership = db.add.call_args_list[1][0][0]
    assert isinstance(added_membership, TenantMembership)
    assert added_membership.role == "owner"
    assert added_membership.user_id == 3


@pytest.mark.asyncio
async def test_remove_member_owner_raises_400() -> None:
    m = _make_membership(role="owner")
    db = _fake_db()
    db.execute.return_value = result([m])

    with pytest.raises(HTTPException) as exc:
        await tenant_service.remove_member(db, tenant_id=1, user_id=1)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_remove_member_not_found_raises_404() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    with pytest.raises(HTTPException) as exc:
        await tenant_service.remove_member(db, tenant_id=1, user_id=99)

    assert exc.value.status_code == 404

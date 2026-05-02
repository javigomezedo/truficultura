from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from tests.conftest import result

from app.models.tenant import TenantInvitation, TenantMembership
from app.models.user import User
from app.services import invitation_service


# ── helpers ───────────────────────────────────────────────────────────────────

_NOW = datetime.datetime(2025, 6, 1, 12, 0, 0, tzinfo=datetime.timezone.utc)
_FUTURE = _NOW + datetime.timedelta(days=7)
_PAST = _NOW - datetime.timedelta(days=1)


def _make_invitation(**kwargs) -> TenantInvitation:
    inv = TenantInvitation()
    inv.id = kwargs.get("id", 1)
    inv.tenant_id = kwargs.get("tenant_id", 1)
    inv.email = kwargs.get("email", "user@example.com")
    inv.token = kwargs.get("token", "tok123")
    inv.role = kwargs.get("role", "member")
    inv.expires_at = kwargs.get("expires_at", _FUTURE)
    inv.accepted_at = kwargs.get("accepted_at", None)
    inv.invited_by_user_id = kwargs.get("invited_by_user_id", 1)
    return inv


def _make_membership(**kwargs) -> TenantMembership:
    m = TenantMembership()
    m.id = kwargs.get("id", 10)
    m.tenant_id = kwargs.get("tenant_id", 1)
    m.user_id = kwargs.get("user_id", 2)
    m.role = kwargs.get("role", "member")
    m.invited_by_user_id = kwargs.get("invited_by_user_id", 1)
    return m


def _fake_db(*execute_results) -> MagicMock:
    """Return a mock DB whose execute is called sequentially with *execute_results."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(execute_results))
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    db.add = MagicMock()
    return db


# ── create_invitation ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_invitation_new() -> None:
    """Creates a fresh invitation when no existing user or pending invite."""
    db = _fake_db(
        result([]),  # User lookup → not found
        result([]),  # Existing invitation lookup → none
    )

    with patch("app.services.invitation_service.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = _NOW
        mock_dt.timedelta.side_effect = datetime.timedelta

        inv = await invitation_service.create_invitation(
            db,
            tenant_id=1,
            email="nuevo@example.com",
            invited_by_user_id=1,
            role="member",
        )

    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    assert inv.email == "nuevo@example.com"


@pytest.mark.asyncio
async def test_create_invitation_reuses_pending() -> None:
    """Reuses and refreshes an existing pending invitation for the same email."""
    existing = _make_invitation(token="old-token", expires_at=_PAST)
    db = _fake_db(
        result([]),  # User lookup → not found
        result([existing]),  # Existing invitation → found
    )

    with patch("app.services.invitation_service.datetime") as mock_dt:
        mock_dt.datetime.now.return_value = _NOW
        mock_dt.timedelta.side_effect = datetime.timedelta

        inv = await invitation_service.create_invitation(
            db,
            tenant_id=1,
            email="user@example.com",
            invited_by_user_id=1,
            role="admin",
        )

    assert inv is existing
    assert inv.token != "old-token"  # regenerated
    assert inv.role == "admin"
    db.add.assert_not_called()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_invitation_email_already_member_raises_400() -> None:
    """Raises 400 when the invited email already belongs to a tenant member."""
    user = User()
    user.id = 5
    user.email = "member@example.com"

    membership = _make_membership(user_id=5)

    db = _fake_db(
        result([user]),  # User lookup → found
        result([membership]),  # Membership check → found
    )

    with pytest.raises(HTTPException) as exc:
        await invitation_service.create_invitation(
            db,
            tenant_id=1,
            email="member@example.com",
            invited_by_user_id=1,
        )

    assert exc.value.status_code == 400


# ── list_pending_invitations ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pending_invitations_returns_list() -> None:
    inv1 = _make_invitation(id=1)
    inv2 = _make_invitation(id=2, email="other@example.com")
    db = _fake_db(result([inv1, inv2]))

    invs = await invitation_service.list_pending_invitations(db, tenant_id=1)

    assert len(invs) == 2
    assert inv1 in invs


@pytest.mark.asyncio
async def test_list_pending_invitations_empty() -> None:
    db = _fake_db(result([]))

    invs = await invitation_service.list_pending_invitations(db, tenant_id=1)

    assert invs == []


# ── revoke_invitation ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_revoke_invitation_success() -> None:
    inv = _make_invitation()
    db = _fake_db(result([inv]))

    await invitation_service.revoke_invitation(db, invitation_id=1, tenant_id=1)

    db.delete.assert_awaited_once_with(inv)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_invitation_not_found_raises_404() -> None:
    db = _fake_db(result([]))

    with pytest.raises(HTTPException) as exc:
        await invitation_service.revoke_invitation(db, invitation_id=99, tenant_id=1)

    assert exc.value.status_code == 404


# ── get_invitation_for_token ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_invitation_for_token_valid() -> None:
    inv = _make_invitation(expires_at=_FUTURE)

    with patch(
        "app.services.invitation_service._get_invitation_by_token",
        AsyncMock(return_value=inv),
    ):
        with patch("app.services.invitation_service.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _NOW

            found = await invitation_service.get_invitation_for_token(
                MagicMock(), "tok123"
            )

    assert found is inv


@pytest.mark.asyncio
async def test_get_invitation_for_token_expired_returns_none() -> None:
    inv = _make_invitation(expires_at=_PAST)

    with patch(
        "app.services.invitation_service._get_invitation_by_token",
        AsyncMock(return_value=inv),
    ):
        with patch("app.services.invitation_service.datetime") as mock_dt:
            mock_dt.datetime.now.return_value = _NOW

            found = await invitation_service.get_invitation_for_token(
                MagicMock(), "tok123"
            )

    assert found is None


@pytest.mark.asyncio
async def test_get_invitation_for_token_already_accepted_returns_none() -> None:
    inv = _make_invitation(accepted_at=_PAST)

    with patch(
        "app.services.invitation_service._get_invitation_by_token",
        AsyncMock(return_value=inv),
    ):
        found = await invitation_service.get_invitation_for_token(MagicMock(), "tok123")

    assert found is None


@pytest.mark.asyncio
async def test_get_invitation_for_token_not_found_returns_none() -> None:
    with patch(
        "app.services.invitation_service._get_invitation_by_token",
        AsyncMock(return_value=None),
    ):
        found = await invitation_service.get_invitation_for_token(
            MagicMock(), "bad-token"
        )

    assert found is None


# ── accept_invitation ─────────────────────────────────────────────────────────


def _make_user(user_id: int = 5, email: str = "user@example.com") -> User:
    u = User()
    u.id = user_id
    u.email = email
    return u


@pytest.mark.asyncio
async def test_accept_invitation_creates_membership() -> None:
    inv = _make_invitation(role="admin", email="user@example.com")
    user = _make_user(user_id=5, email="user@example.com")

    # 1st execute: User lookup for email validation → user
    # 2nd execute: check existing membership in target tenant → none
    # 3rd execute: find previous memberships in other tenants → none
    db = _fake_db(result([user]), result([]), result([]))

    with patch(
        "app.services.invitation_service.get_invitation_for_token",
        AsyncMock(return_value=inv),
    ):
        membership = await invitation_service.accept_invitation(
            db, token="tok123", user_id=5
        )

    db.add.assert_called_once()
    # flush se llama dos veces: una tras eliminar membresías antiguas y otra al final
    assert db.flush.await_count >= 1
    assert membership.role == "admin"
    assert inv.accepted_at is not None


@pytest.mark.asyncio
async def test_accept_invitation_removes_previous_membership() -> None:
    """Al aceptar una invitación se elimina la membresía previa (solo-tenant) y el tenant huérfano."""
    inv = _make_invitation(tenant_id=99, role="member", email="user@example.com")
    old_membership = _make_membership(tenant_id=1, user_id=5)
    user = _make_user(user_id=5, email="user@example.com")

    # Make a solo-tenant with no Stripe customer (safe to delete)
    from unittest.mock import MagicMock

    old_tenant = MagicMock()
    old_tenant.id = 1
    old_tenant.stripe_customer_id = None

    # 1st execute: User lookup for email validation → user
    # 2nd execute: check existing membership in target tenant (99) → none
    # 3rd execute: find previous memberships in other tenants → old_membership
    # (flush happens here)
    # 4th execute: check remaining members in old tenant (1) → none (orphaned)
    # 5th execute: fetch old tenant → old_tenant (stripe_customer_id=None → safe to delete)
    db = _fake_db(
        result([user]),
        result([]),
        result([old_membership]),
        result([]),  # no remaining members in old tenant
        result([old_tenant]),  # old tenant fetched for deletion
    )
    db.delete = AsyncMock()

    with patch(
        "app.services.invitation_service.get_invitation_for_token",
        AsyncMock(return_value=inv),
    ):
        membership = await invitation_service.accept_invitation(
            db, token="tok123", user_id=5
        )

    # delete called for: old_membership + orphaned old_tenant
    assert db.delete.await_count == 2
    db.delete.assert_any_await(old_membership)
    db.delete.assert_any_await(old_tenant)
    db.add.assert_called_once()
    assert membership.role == "member"


@pytest.mark.asyncio
async def test_accept_invitation_keeps_tenant_with_stripe() -> None:
    """No elimina el tenant huérfano si tiene stripe_customer_id (datos de billing)."""
    from unittest.mock import MagicMock

    inv = _make_invitation(tenant_id=99, role="member", email="user@example.com")
    old_membership = _make_membership(tenant_id=1, user_id=5)
    user = _make_user(user_id=5, email="user@example.com")

    stripe_tenant = MagicMock()
    stripe_tenant.id = 1
    stripe_tenant.stripe_customer_id = "cus_abc123"

    db = _fake_db(
        result([user]),
        result([]),
        result([old_membership]),
        result([]),  # no remaining members
        result([stripe_tenant]),  # tenant has Stripe → must NOT be deleted
    )
    db.delete = AsyncMock()

    with patch(
        "app.services.invitation_service.get_invitation_for_token",
        AsyncMock(return_value=inv),
    ):
        await invitation_service.accept_invitation(db, token="tok123", user_id=5)

    # Only the membership is deleted, NOT the tenant
    db.delete.assert_awaited_once_with(old_membership)


@pytest.mark.asyncio
async def test_accept_invitation_wrong_email_raises_403() -> None:
    """Rechaza la aceptación si el email del usuario no coincide con el de la invitación."""
    inv = _make_invitation(email="invitado@example.com")
    user = _make_user(user_id=5, email="otro@example.com")

    db = _fake_db(result([user]))

    with patch(
        "app.services.invitation_service.get_invitation_for_token",
        AsyncMock(return_value=inv),
    ):
        with pytest.raises(HTTPException) as exc:
            await invitation_service.accept_invitation(db, token="tok123", user_id=5)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_accept_invitation_idempotent_if_already_member() -> None:
    inv = _make_invitation(role="member", email="user@example.com")
    existing = _make_membership(user_id=5)
    user = _make_user(user_id=5, email="user@example.com")

    # 1st execute: User lookup for email validation → user
    # 2nd execute: already a member
    db = _fake_db(result([user]), result([existing]))

    with patch(
        "app.services.invitation_service.get_invitation_for_token",
        AsyncMock(return_value=inv),
    ):
        membership = await invitation_service.accept_invitation(
            db, token="tok123", user_id=5
        )

    assert membership is existing
    db.add.assert_not_called()
    assert inv.accepted_at is not None


@pytest.mark.asyncio
async def test_accept_invitation_invalid_token_raises_400() -> None:
    db = _fake_db()

    with patch(
        "app.services.invitation_service.get_invitation_for_token",
        AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await invitation_service.accept_invitation(db, token="bad-token", user_id=5)

    assert exc.value.status_code == 400

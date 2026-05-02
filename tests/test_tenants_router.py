"""Tests for app.routers.tenants."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.auth import require_user
from app.database import get_db
from app.main import app


# ── helpers ───────────────────────────────────────────────────────────────────


def _user(**kwargs):
    defaults = dict(
        id=1,
        role="user",
        is_active=True,
        email="owner@example.com",
        first_name="Owner",
        last_name="User",
        active_tenant_id=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _db():
    db = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    return db


def _membership(role: str = "owner", user_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        tenant_id=1,
        user_id=user_id,
        role=role,
    )


def _tenant() -> SimpleNamespace:
    return SimpleNamespace(id=1, name="Finca Demo", slug="finca-demo")


def _invitation(**kwargs) -> SimpleNamespace:
    import datetime

    defaults = dict(
        id=1,
        tenant_id=1,
        email="guest@example.com",
        token="tok-abc",
        role="member",
        expires_at=datetime.datetime(2030, 1, 1),
        accepted_at=None,
        invited_by_user_id=1,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ── GET /tenant/settings ──────────────────────────────────────────────────────


def test_settings_page_renders() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_tenant",
            AsyncMock(return_value=_tenant()),
        ),
        patch(
            "app.routers.tenants.tenant_service.list_members",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.routers.tenants.invitation_service.list_pending_invitations",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership()),
        ),
    ):
        try:
            response = TestClient(app).get("/tenant/settings")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Finca Demo" in response.text


# ── POST /tenant/settings ─────────────────────────────────────────────────────


def test_settings_post_updates_name() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.tenant_service.update_tenant",
            AsyncMock(return_value=_tenant()),
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/settings", data={"name": "Nueva Finca"}, follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "saved=1" in response.headers["location"]


def test_settings_post_forbidden_for_member() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with patch(
        "app.routers.tenants.tenant_service.get_membership",
        AsyncMock(return_value=_membership("member")),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/settings", data={"name": "X"}, follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=forbidden" in response.headers["location"]


# ── POST /tenant/members/{user_id}/role ───────────────────────────────────────


def test_change_member_role_success() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.tenant_service.change_member_role",
            AsyncMock(return_value=_membership("admin", 2)),
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/members/2/role", data={"role": "admin"}, follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "saved=1" in response.headers["location"]


def test_change_member_role_forbidden_for_member() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with patch(
        "app.routers.tenants.tenant_service.get_membership",
        AsyncMock(return_value=_membership("member")),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/members/2/role", data={"role": "admin"}, follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=forbidden" in response.headers["location"]


# ── POST /tenant/members/{user_id}/remove ─────────────────────────────────────


def test_remove_member_success() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.tenant_service.remove_member",
            AsyncMock(return_value=None),
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/members/2/remove", follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "saved=1" in response.headers["location"]


def test_remove_member_forbidden_for_member() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with patch(
        "app.routers.tenants.tenant_service.get_membership",
        AsyncMock(return_value=_membership("member")),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/members/2/remove", follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=forbidden" in response.headers["location"]


# ── POST /tenant/invitations/send ─────────────────────────────────────────────


def test_send_invitation_success() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    inv = _invitation()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.invitation_service.create_invitation",
            AsyncMock(return_value=inv),
        ),
        patch(
            "app.routers.tenants.tenant_service.get_tenant",
            AsyncMock(return_value=_tenant()),
        ),
        patch("app.routers.tenants.settings") as mock_settings,
    ):
        mock_settings.email_configured = False
        try:
            response = TestClient(app).post(
                "/tenant/invitations/send",
                data={"email": "guest@example.com", "role": "member"},
                follow_redirects=False,
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "invited=1" in response.headers["location"]


def test_send_invitation_invalid_email() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with patch(
        "app.routers.tenants.tenant_service.get_membership",
        AsyncMock(return_value=_membership("owner")),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/invitations/send",
                data={"email": "not-an-email", "role": "member"},
                follow_redirects=False,
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=invalid_email" in response.headers["location"]


def test_send_invitation_forbidden_for_member() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with patch(
        "app.routers.tenants.tenant_service.get_membership",
        AsyncMock(return_value=_membership("member")),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/invitations/send",
                data={"email": "x@x.com", "role": "member"},
                follow_redirects=False,
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=forbidden" in response.headers["location"]


def test_send_invitation_email_already_member_redirects() -> None:
    """Si el email ya es miembro, el router redirige con error=already_member."""
    from fastapi import HTTPException as FHTTPException

    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.invitation_service.create_invitation",
            AsyncMock(
                side_effect=FHTTPException(
                    status_code=400, detail="Ese email ya es miembro"
                )
            ),
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/invitations/send",
                data={"email": "owner@example.com", "role": "member"},
                follow_redirects=False,
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=already_member" in response.headers["location"]


# ── POST /tenant/invitations/{id}/revoke ──────────────────────────────────────


def test_revoke_invitation_success() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.invitation_service.revoke_invitation",
            AsyncMock(return_value=None),
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/invitations/1/revoke", follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "saved=1" in response.headers["location"]


def test_revoke_invitation_forbidden_for_member() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with patch(
        "app.routers.tenants.tenant_service.get_membership",
        AsyncMock(return_value=_membership("member")),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/invitations/1/revoke", follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=forbidden" in response.headers["location"]


# ── GET /tenant/join/{token} ──────────────────────────────────────────────────


def test_join_get_valid_token_renders() -> None:
    user = _user(email="guest@example.com")  # matches invitation email
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    inv = _invitation()  # email="guest@example.com"

    with (
        patch(
            "app.routers.tenants.invitation_service.get_invitation_for_token",
            AsyncMock(return_value=inv),
        ),
        patch(
            "app.routers.tenants.tenant_service.get_tenant",
            AsyncMock(return_value=_tenant()),
        ),
    ):
        try:
            response = TestClient(app).get("/tenant/join/tok-abc")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Finca Demo" in response.text
    assert "Aceptar invitación" in response.text


def test_join_get_email_mismatch_shows_error() -> None:
    """Si el usuario logueado no es el destinatario de la invitación, se muestra error."""
    user = _user(email="other@example.com")  # does NOT match invitation email
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    inv = _invitation()  # email="guest@example.com"

    with (
        patch(
            "app.routers.tenants.invitation_service.get_invitation_for_token",
            AsyncMock(return_value=inv),
        ),
        patch(
            "app.routers.tenants.tenant_service.get_tenant",
            AsyncMock(return_value=_tenant()),
        ),
    ):
        try:
            response = TestClient(app).get("/tenant/join/tok-abc")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "guest@example.com" in response.text  # error shows the intended email
    assert "Aceptar invitación" not in response.text  # form is hidden


def test_join_get_invalid_token_returns_400() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with patch(
        "app.routers.tenants.invitation_service.get_invitation_for_token",
        AsyncMock(return_value=None),
    ):
        try:
            response = TestClient(app).get("/tenant/join/bad-token")
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 400


# ── POST /tenant/join/{token} ─────────────────────────────────────────────────


def test_join_post_accepts_invitation() -> None:
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    membership = _membership("member", 1)

    with patch(
        "app.routers.tenants.invitation_service.accept_invitation",
        AsyncMock(return_value=membership),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/join/tok-abc", follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "joined=1" in response.headers["location"]


def test_join_post_invalid_token_redirects_back() -> None:
    """Si accept_invitation lanza HTTPException, redirige al GET de join (no JSON)."""
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with patch(
        "app.routers.tenants.invitation_service.accept_invitation",
        AsyncMock(
            side_effect=HTTPException(status_code=400, detail="Invitación expirada")
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/join/bad-token", follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/tenant/join/bad-token" in response.headers["location"]


# ── Exceptions from service layer redirect instead of JSON ────────────────────


def test_change_member_role_service_error_redirects_with_forbidden() -> None:
    """Si el servicio lanza HTTPException (p.ej. intentar cambiar rol del owner),
    el router redirige con ?error=forbidden en vez de devolver JSON."""
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.tenant_service.change_member_role",
            AsyncMock(
                side_effect=HTTPException(
                    status_code=400, detail="No se puede cambiar el rol del propietario"
                )
            ),
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/members/2/role",
                data={"role": "member"},
                follow_redirects=False,
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=forbidden" in response.headers["location"]


def test_remove_member_service_error_redirects_with_forbidden() -> None:
    """Si el servicio lanza HTTPException (p.ej. intentar eliminar al owner),
    el router redirige con ?error=forbidden en vez de devolver JSON."""
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.tenant_service.remove_member",
            AsyncMock(
                side_effect=HTTPException(
                    status_code=400, detail="No se puede eliminar al propietario"
                )
            ),
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/members/2/remove", follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=forbidden" in response.headers["location"]


def test_revoke_invitation_service_error_redirects_with_forbidden() -> None:
    """Si el servicio lanza HTTPException (invitación no encontrada),
    el router redirige con ?error=forbidden en vez de devolver JSON."""
    user = _user()
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: _db()

    with (
        patch(
            "app.routers.tenants.tenant_service.get_membership",
            AsyncMock(return_value=_membership("owner")),
        ),
        patch(
            "app.routers.tenants.invitation_service.revoke_invitation",
            AsyncMock(
                side_effect=HTTPException(
                    status_code=404, detail="Invitación no encontrada"
                )
            ),
        ),
    ):
        try:
            response = TestClient(app).post(
                "/tenant/invitations/99/revoke", follow_redirects=False
            )
        finally:
            app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "error=forbidden" in response.headers["location"]

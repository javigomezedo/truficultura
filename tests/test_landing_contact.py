"""Tests for POST /landing/contact endpoint and send_lead_notification."""

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app

# send_lead_notification is imported inside the endpoint body, so patch at service level
_PATCH_NOTIFY = "app.services.email_service.send_lead_notification"


class _ScalarsResult:
    """Minimal mock of SQLAlchemy scalars() result."""

    def __init__(self, items: list) -> None:
        self._items = items

    def first(self):
        return self._items[0] if self._items else None

    def all(self) -> list:
        return self._items


class _ExecuteResult:
    def __init__(self, items: list) -> None:
        self._items = items

    def scalars(self) -> _ScalarsResult:
        return _ScalarsResult(self._items)

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None


def _fake_db(existing_lead=None) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=_ExecuteResult([existing_lead] if existing_lead else [])
    )
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# POST /landing/contact — endpoint tests
# ---------------------------------------------------------------------------


def test_landing_contact_creates_lead() -> None:
    db = _fake_db()
    app.dependency_overrides[get_db] = lambda: db

    with patch(_PATCH_NOTIFY, new=AsyncMock()):
        client = TestClient(app)
        resp = client.post(
            "/landing/contact",
            data={
                "name": "Javier",
                "email": "javier@example.com",
                "message": "Quiero una demo",
            },
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


def test_landing_contact_without_message() -> None:
    db = _fake_db()
    app.dependency_overrides[get_db] = lambda: db

    with patch(_PATCH_NOTIFY, new=AsyncMock()):
        client = TestClient(app)
        resp = client.post(
            "/landing/contact",
            data={"name": "Javier", "email": "javier@example.com"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_landing_contact_invalid_email_returns_422() -> None:
    db = _fake_db()
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    resp = client.post(
        "/landing/contact",
        data={"name": "Javier", "email": "not-an-email"},
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 422
    assert resp.json()["ok"] is False


def test_landing_contact_empty_name_returns_422() -> None:
    db = _fake_db()
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    resp = client.post(
        "/landing/contact",
        data={"name": "   ", "email": "javier@example.com"},
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 422


def test_landing_contact_deduplicates_within_24h() -> None:
    from app.models.lead_capture import LeadCapture

    existing = LeadCapture(
        id=1,
        name="Javier",
        email="javier@example.com",
        created_at=datetime.datetime.now(datetime.timezone.utc),
    )
    db = _fake_db(existing_lead=existing)
    app.dependency_overrides[get_db] = lambda: db

    client = TestClient(app)
    resp = client.post(
        "/landing/contact",
        data={"name": "Javier", "email": "javier@example.com"},
    )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # No debe insertar un segundo lead
    db.add.assert_not_called()


def test_landing_contact_email_error_does_not_crash() -> None:
    """Si send_lead_notification lanza excepción, el endpoint devuelve ok igual."""
    db = _fake_db()
    app.dependency_overrides[get_db] = lambda: db

    with patch(
        _PATCH_NOTIFY,
        new=AsyncMock(side_effect=Exception("SMTP down")),
    ):
        client = TestClient(app)
        resp = client.post(
            "/landing/contact",
            data={"name": "Javier", "email": "javier@example.com"},
        )

    app.dependency_overrides.clear()
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


# ---------------------------------------------------------------------------
# send_lead_notification — service tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_lead_notification_skips_when_no_backend_configured() -> None:
    from app.services.email_service import send_lead_notification

    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.postmark_configured = False
        mock_settings.email_configured = False
        mock_settings.CONTACT_EMAIL = None
        mock_settings.effective_from = "noreply@example.com"

        with patch(
            "app.services.email_service.send_email", new=AsyncMock()
        ) as mock_send:
            await send_lead_notification(name="Javier", email="javier@example.com")
            mock_send.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_lead_notification_sends_email_when_postmark_configured() -> None:
    from app.services.email_service import send_lead_notification

    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.postmark_configured = True
        mock_settings.email_configured = True
        mock_settings.CONTACT_EMAIL = "admin@example.com"
        mock_settings.effective_from = "noreply@example.com"
        mock_settings.APP_BASE_URL = "http://localhost:8000"

        with patch(
            "app.services.email_service.send_email", new=AsyncMock()
        ) as mock_send:
            await send_lead_notification(
                name="Javier", email="javier@example.com", message="Quiero una demo"
            )
            mock_send.assert_awaited_once()
            subject = mock_send.call_args[0][1]
            assert "Javier" in subject


@pytest.mark.asyncio
async def test_send_lead_notification_without_message() -> None:
    from app.services.email_service import send_lead_notification

    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.postmark_configured = True
        mock_settings.email_configured = True
        mock_settings.CONTACT_EMAIL = "admin@example.com"
        mock_settings.effective_from = "noreply@example.com"
        mock_settings.APP_BASE_URL = "http://localhost:8000"

        with patch(
            "app.services.email_service.send_email", new=AsyncMock()
        ) as mock_send:
            await send_lead_notification(name="Javier", email="javier@example.com")
            mock_send.assert_awaited_once()
            html = mock_send.call_args[0][2]
            assert "Mensaje" not in html

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import httpx

from types import SimpleNamespace

from app.services.email_service import (
    _send_via_postmark,
    _send_via_smtp,
    send_confirmation_email,
    send_email,
    send_incident_notification,
    send_incident_resolved_email,
    send_password_reset_email,
    send_welcome_email,
)


@pytest.mark.asyncio
async def test_send_email_skips_when_no_backend_configured(monkeypatch) -> None:
    """When neither Postmark nor SMTP is configured, no call is made."""
    monkeypatch.setattr(
        "app.services.email_service.settings",
        type("S", (), {"postmark_configured": False, "smtp_configured": False})(),
    )
    with patch("app.services.email_service._send_via_postmark", new_callable=AsyncMock) as mock_pm, \
         patch("app.services.email_service._send_via_smtp", new_callable=AsyncMock) as mock_smtp:
        await send_email("to@example.com", "Subject", "<p>body</p>")
        mock_pm.assert_not_called()
        mock_smtp.assert_not_called()


@pytest.mark.asyncio
async def test_send_email_uses_postmark_when_configured(monkeypatch) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "postmark_configured": True,
            "smtp_configured": False,
            "POSTMARK_API_KEY": "test-key",
            "effective_from": "noreply@example.com",
        },
    )()
    monkeypatch.setattr("app.services.email_service.settings", fake_settings)

    with patch("app.services.email_service._send_via_postmark", new_callable=AsyncMock) as mock_pm:
        await send_email("to@example.com", "Hello", "<p>hi</p>")
        mock_pm.assert_awaited_once_with("to@example.com", "Hello", "<p>hi</p>", "noreply@example.com")


@pytest.mark.asyncio
async def test_send_email_falls_back_to_smtp_when_postmark_not_configured(monkeypatch) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "postmark_configured": False,
            "smtp_configured": True,
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": 587,
            "SMTP_USER": "user",
            "SMTP_PASSWORD": "pass",
            "SMTP_FROM": "noreply@example.com",
            "SMTP_TLS": True,
            "SMTP_SSL": False,
        },
    )()
    monkeypatch.setattr("app.services.email_service.settings", fake_settings)

    with patch("app.services.email_service._send_via_smtp", new_callable=AsyncMock) as mock_smtp:
        await send_email("to@example.com", "Hello", "<p>hi</p>")
        mock_smtp.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_email_falls_back_to_smtp_when_postmark_fails(monkeypatch) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "postmark_configured": True,
            "smtp_configured": True,
            "POSTMARK_API_KEY": "test-key",
            "effective_from": "hola@trufiq.app",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": 587,
            "SMTP_USER": "user",
            "SMTP_PASSWORD": "pass",
            "SMTP_FROM": "noreply@example.com",
            "SMTP_TLS": True,
            "SMTP_SSL": False,
        },
    )()
    monkeypatch.setattr("app.services.email_service.settings", fake_settings)

    with patch(
        "app.services.email_service._send_via_postmark",
        new=AsyncMock(side_effect=RuntimeError("postmark down")),
    ) as mock_pm, patch("app.services.email_service._send_via_smtp", new_callable=AsyncMock) as mock_smtp:
        await send_email("to@example.com", "Hello", "<p>hi</p>")
        mock_pm.assert_awaited_once()
        mock_smtp.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_confirmation_email_contains_confirm_url(monkeypatch) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "postmark_configured": True,
            "smtp_configured": False,
            "effective_from": "noreply@example.com",
            "APP_BASE_URL": "https://app.example.com",
        },
    )()
    monkeypatch.setattr("app.services.email_service.settings", fake_settings)

    sent_html: list[str] = []

    async def capture_send(to, subject, html_body):
        sent_html.append(html_body)

    monkeypatch.setattr("app.services.email_service.send_email", capture_send)
    await send_confirmation_email("user@example.com", "abc123")

    assert len(sent_html) == 1
    assert "https://app.example.com/register/confirm/abc123" in sent_html[0]


@pytest.mark.asyncio
async def test_send_password_reset_email_contains_reset_url(monkeypatch) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "postmark_configured": True,
            "smtp_configured": False,
            "effective_from": "noreply@example.com",
            "APP_BASE_URL": "https://app.example.com",
        },
    )()
    monkeypatch.setattr("app.services.email_service.settings", fake_settings)

    sent_html: list[str] = []

    async def capture_send(to, subject, html_body):
        sent_html.append(html_body)

    monkeypatch.setattr("app.services.email_service.send_email", capture_send)
    await send_password_reset_email("user@example.com", "xyz789")

    assert len(sent_html) == 1
    assert "https://app.example.com/reset-password/xyz789" in sent_html[0]


@pytest.mark.asyncio
async def test_send_via_postmark_success(monkeypatch) -> None:
    """_send_via_postmark makes the HTTP call and logs the message ID."""
    monkeypatch.setattr(
        "app.services.email_service.settings",
        type("S", (), {"POSTMARK_API_KEY": "test-key"})(),
    )
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"MessageID": "abc-123"}

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.services.email_service.httpx.AsyncClient", return_value=mock_client):
        await _send_via_postmark("to@example.com", "Subject", "<p>hi</p>", "from@example.com")

    mock_client.post.assert_awaited_once()
    mock_response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_send_via_postmark_logs_and_reraises_on_http_error(monkeypatch) -> None:
    """_send_via_postmark logs error details and re-raises HTTPStatusError."""
    monkeypatch.setattr(
        "app.services.email_service.settings",
        type("S", (), {"POSTMARK_API_KEY": "test-key"})(),
    )
    mock_request = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 422
    mock_resp.text = '{"ErrorCode": 412, "Message": "domain mismatch"}'
    error = httpx.HTTPStatusError("422", request=mock_request, response=mock_resp)

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(side_effect=error)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("app.services.email_service.httpx.AsyncClient", return_value=mock_client):
        with pytest.raises(httpx.HTTPStatusError):
            await _send_via_postmark("to@example.com", "Subject", "<p>hi</p>", "from@example.com")


@pytest.mark.asyncio
async def test_send_via_smtp_sends_message(monkeypatch) -> None:
    """_send_via_smtp builds the MIME message and calls aiosmtplib.send."""
    monkeypatch.setattr(
        "app.services.email_service.settings",
        type(
            "S",
            (),
            {
                "SMTP_FROM": "noreply@example.com",
                "SMTP_HOST": "smtp.example.com",
                "SMTP_PORT": 587,
                "SMTP_USER": "user",
                "SMTP_PASSWORD": "pass",
                "SMTP_TLS": True,
                "SMTP_SSL": False,
            },
        )(),
    )
    with patch("app.services.email_service.aiosmtplib.send", new=AsyncMock()) as mock_send:
        await _send_via_smtp("to@example.com", "Subject", "<p>hi</p>")
        mock_send.assert_awaited_once()


@pytest.mark.asyncio
async def test_send_email_reraises_when_postmark_fails_and_no_smtp(monkeypatch) -> None:
    """When Postmark fails and SMTP is not configured, the exception propagates."""
    fake_settings = type(
        "S",
        (),
        {
            "postmark_configured": True,
            "smtp_configured": False,
            "effective_from": "hola@trufiq.app",
        },
    )()
    monkeypatch.setattr("app.services.email_service.settings", fake_settings)

    with patch(
        "app.services.email_service._send_via_postmark",
        new=AsyncMock(side_effect=RuntimeError("postmark down")),
    ):
        with pytest.raises(RuntimeError, match="postmark down"):
            await send_email("to@example.com", "Hello", "<p>hi</p>")


@pytest.mark.asyncio
async def test_send_welcome_email_contains_first_name_and_dashboard_url(monkeypatch) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "postmark_configured": True,
            "smtp_configured": False,
            "effective_from": "noreply@example.com",
            "APP_BASE_URL": "https://app.example.com",
        },
    )()
    monkeypatch.setattr("app.services.email_service.settings", fake_settings)

    sent_html: list[str] = []

    async def capture_send(to, subject, html_body):
        sent_html.append(html_body)

    monkeypatch.setattr("app.services.email_service.send_email", capture_send)
    await send_welcome_email("María", "maria@example.com")

    assert len(sent_html) == 1
    assert "María" in sent_html[0]
    assert "https://app.example.com/" in sent_html[0]
    assert "https://app.example.com/plots/new" in sent_html[0]


# ---------------------------------------------------------------------------
# send_incident_notification
# ---------------------------------------------------------------------------


def _fake_incident_settings():
    return type(
        "S",
        (),
        {
            "email_configured": True,
            "postmark_configured": True,
            "smtp_configured": False,
            "effective_from": "noreply@example.com",
            "CONTACT_EMAIL": "admin@example.com",
            "APP_BASE_URL": "https://app.example.com",
        },
    )()


def _fake_incident(incident_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=incident_id,
        title="Error en el botón",
        category_label="Botón roto",
        severity_label="Alta",
    )


def _fake_user() -> SimpleNamespace:
    return SimpleNamespace(
        first_name="Juan",
        last_name="García",
        email="juan@example.com",
    )


@pytest.mark.asyncio
async def test_send_incident_notification_skips_when_no_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.email_service.settings",
        type("S", (), {"email_configured": False, "CONTACT_EMAIL": None, "effective_from": "x@x.com"})(),
    )
    sent: list[str] = []

    async def capture(to, subject, html_body):
        sent.append(to)

    monkeypatch.setattr("app.services.email_service.send_email", capture)
    await send_incident_notification(incident=_fake_incident(), user=_fake_user())

    assert sent == []


@pytest.mark.asyncio
async def test_send_incident_notification_sends_to_contact_email(monkeypatch) -> None:
    monkeypatch.setattr("app.services.email_service.settings", _fake_incident_settings())

    sent_to: list[str] = []
    sent_subjects: list[str] = []
    sent_bodies: list[str] = []

    async def capture(to, subject, html_body):
        sent_to.append(to)
        sent_subjects.append(subject)
        sent_bodies.append(html_body)

    monkeypatch.setattr("app.services.email_service.send_email", capture)
    await send_incident_notification(incident=_fake_incident(1), user=_fake_user())

    assert sent_to == ["admin@example.com"]
    assert "Error en el botón" in sent_subjects[0]
    assert "Alta" in sent_subjects[0]
    assert "https://app.example.com/incidents/admin/1" in sent_bodies[0]
    assert "Botón roto" in sent_bodies[0]
    assert "Juan" in sent_bodies[0]


@pytest.mark.asyncio
async def test_send_incident_notification_escapes_html(monkeypatch) -> None:
    monkeypatch.setattr("app.services.email_service.settings", _fake_incident_settings())

    sent_bodies: list[str] = []

    async def capture(to, subject, html_body):
        sent_bodies.append(html_body)

    monkeypatch.setattr("app.services.email_service.send_email", capture)

    malicious_incident = SimpleNamespace(
        id=1,
        title="<script>alert('xss')</script>",
        category_label="<b>bold</b>",
        severity_label="Alta",
    )
    malicious_user = SimpleNamespace(
        first_name="<img src=x>",
        last_name="",
        email="bad@x.com",
    )
    await send_incident_notification(incident=malicious_incident, user=malicious_user)

    assert "<script>" not in sent_bodies[0]
    assert "&lt;script&gt;" in sent_bodies[0]


# ---------------------------------------------------------------------------
# send_incident_resolved_email
# ---------------------------------------------------------------------------


def _fake_resolved_incident() -> SimpleNamespace:
    return SimpleNamespace(
        id=5,
        title="Error en el botón",
        admin_response="Se ha corregido en la versión 1.2.",
        user=SimpleNamespace(email="juan@example.com"),
    )


@pytest.mark.asyncio
async def test_send_incident_resolved_email_no_user_skips(monkeypatch) -> None:
    inc = _fake_resolved_incident()
    inc.user = None

    sent: list[str] = []

    async def capture(to, subject, html_body):
        sent.append(to)

    monkeypatch.setattr("app.services.email_service.send_email", capture)
    await send_incident_resolved_email(incident=inc)

    assert sent == []


@pytest.mark.asyncio
async def test_send_incident_resolved_email_no_email_address_skips(monkeypatch) -> None:
    inc = _fake_resolved_incident()
    inc.user = SimpleNamespace(email=None)

    sent: list[str] = []

    async def capture(to, subject, html_body):
        sent.append(to)

    monkeypatch.setattr("app.services.email_service.send_email", capture)
    await send_incident_resolved_email(incident=inc)

    assert sent == []


@pytest.mark.asyncio
async def test_send_incident_resolved_email_skips_when_no_backend(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.email_service.settings",
        type("S", (), {"email_configured": False, "APP_BASE_URL": "https://app.example.com"})(),
    )
    sent: list[str] = []

    async def capture(to, subject, html_body):
        sent.append(to)

    monkeypatch.setattr("app.services.email_service.send_email", capture)
    await send_incident_resolved_email(incident=_fake_resolved_incident())

    assert sent == []


@pytest.mark.asyncio
async def test_send_incident_resolved_email_sends_to_user(monkeypatch) -> None:
    monkeypatch.setattr("app.services.email_service.settings", _fake_incident_settings())

    sent_to: list[str] = []
    sent_subjects: list[str] = []
    sent_bodies: list[str] = []

    async def capture(to, subject, html_body):
        sent_to.append(to)
        sent_subjects.append(subject)
        sent_bodies.append(html_body)

    monkeypatch.setattr("app.services.email_service.send_email", capture)
    await send_incident_resolved_email(incident=_fake_resolved_incident())

    assert sent_to == ["juan@example.com"]
    assert "Error en el botón" in sent_subjects[0]
    assert "Se ha corregido en la versión 1.2." in sent_bodies[0]
    assert "https://app.example.com/incidents/5" in sent_bodies[0]

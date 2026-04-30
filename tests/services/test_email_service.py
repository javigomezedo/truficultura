from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.email_service import (
    send_confirmation_email,
    send_email,
    send_password_reset_email,
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

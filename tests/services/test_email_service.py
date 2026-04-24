from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.email_service import (
    send_confirmation_email,
    send_email,
    send_password_reset_email,
)


@pytest.mark.asyncio
async def test_send_email_skips_when_smtp_not_configured(monkeypatch) -> None:
    """When smtp_configured is False, no SMTP call is made."""
    monkeypatch.setattr(
        "app.services.email_service.settings",
        type("S", (), {"smtp_configured": False, "SMTP_FROM": "noreply@test.com"})(),
    )
    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await send_email("to@example.com", "Subject", "<p>body</p>")
        mock_send.assert_not_called()


@pytest.mark.asyncio
async def test_send_email_calls_aiosmtplib_when_configured(monkeypatch) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "smtp_configured": True,
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": 587,
            "SMTP_USER": "user",
            "SMTP_PASSWORD": "pass",
            "SMTP_FROM": "noreply@example.com",
            "SMTP_TLS": True,
        },
    )()
    monkeypatch.setattr("app.services.email_service.settings", fake_settings)

    with patch("aiosmtplib.send", new_callable=AsyncMock) as mock_send:
        await send_email("to@example.com", "Hello", "<p>hi</p>")
        mock_send.assert_awaited_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["hostname"] == "smtp.example.com"
        assert call_kwargs["port"] == 587
        assert call_kwargs["username"] == "user"


@pytest.mark.asyncio
async def test_send_confirmation_email_contains_confirm_url(monkeypatch) -> None:
    fake_settings = type(
        "S",
        (),
        {
            "smtp_configured": True,
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": 587,
            "SMTP_USER": "u",
            "SMTP_PASSWORD": "p",
            "SMTP_FROM": "noreply@example.com",
            "SMTP_TLS": True,
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
            "smtp_configured": True,
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": 587,
            "SMTP_USER": "u",
            "SMTP_PASSWORD": "p",
            "SMTP_FROM": "noreply@example.com",
            "SMTP_TLS": True,
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

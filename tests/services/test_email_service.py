from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import httpx

from app.services.email_service import (
    _send_via_postmark,
    _send_via_smtp,
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

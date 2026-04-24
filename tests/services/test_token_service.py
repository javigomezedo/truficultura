from __future__ import annotations

import pytest

from app.services.token_service import (
    EMAIL_CONFIRMATION_SALT,
    PASSWORD_RESET_SALT,
    confirm_token,
    generate_token,
)


def test_generate_and_confirm_token_roundtrip() -> None:
    token = generate_token("user@example.com", EMAIL_CONFIRMATION_SALT)
    email = confirm_token(token, EMAIL_CONFIRMATION_SALT, max_age=3600)
    assert email == "user@example.com"


def test_confirm_token_wrong_salt_returns_none() -> None:
    """A token generated with one salt must not be usable with a different salt."""
    token = generate_token("user@example.com", EMAIL_CONFIRMATION_SALT)
    result = confirm_token(token, PASSWORD_RESET_SALT, max_age=3600)
    assert result is None


def test_confirm_token_tampered_returns_none() -> None:
    token = generate_token("user@example.com", EMAIL_CONFIRMATION_SALT)
    tampered = token[:-4] + "XXXX"
    result = confirm_token(tampered, EMAIL_CONFIRMATION_SALT, max_age=3600)
    assert result is None


def test_confirm_token_expired_returns_none(monkeypatch) -> None:
    """Simulate an expired token by advancing time past the max_age window."""
    import time as _time

    token = generate_token("user@example.com", PASSWORD_RESET_SALT)
    frozen_now = _time.time() + 7201  # 2 hours in the future
    monkeypatch.setattr(_time, "time", lambda: frozen_now)
    result = confirm_token(token, PASSWORD_RESET_SALT, max_age=3600)
    assert result is None


def test_password_reset_token_roundtrip() -> None:
    token = generate_token("admin@example.com", PASSWORD_RESET_SALT)
    email = confirm_token(token, PASSWORD_RESET_SALT, max_age=3600)
    assert email == "admin@example.com"

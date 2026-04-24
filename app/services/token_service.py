"""Token generation and validation for email confirmation and password reset.

Uses itsdangerous URLSafeTimedSerializer (already in the stack via SessionMiddleware)
so no extra dependency is needed. Tokens are stateless — no DB column required.

Two salts are used to make tokens non-interchangeable:
    EMAIL_CONFIRMATION_SALT — valid 24 h
    PASSWORD_RESET_SALT     — valid 1 h
"""

from __future__ import annotations

from typing import Optional

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import settings

EMAIL_CONFIRMATION_SALT = "email-confirmation"
PASSWORD_RESET_SALT = "password-reset"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(settings.SECRET_KEY)


def generate_token(payload: str, salt: str) -> str:
    """Sign *payload* (typically an email address) with *salt* and return the token."""
    return _serializer().dumps(payload, salt=salt)


def confirm_token(token: str, salt: str, max_age: int) -> Optional[str]:
    """Verify *token* and return the embedded payload, or None if invalid/expired."""
    try:
        return _serializer().loads(token, salt=salt, max_age=max_age)
    except (SignatureExpired, BadSignature):
        return None

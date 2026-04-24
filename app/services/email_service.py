"""Async email sending via aiosmtplib.

If SMTP is not configured (settings.smtp_configured is False) every send call
is a no-op so the app works normally in development without any mail server.
"""

from __future__ import annotations

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(to: str, subject: str, html_body: str) -> None:
    """Send an HTML email to *to*.  Silently skips when SMTP is not configured."""
    if not settings.smtp_configured:
        logger.info(
            "[email] SMTP not configured — skipping send to %s: %s", to, subject
        )
        return

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message.attach(MIMEText(html_body, "html", "utf-8"))

    await aiosmtplib.send(
        message,
        hostname=settings.SMTP_HOST,
        port=settings.SMTP_PORT,
        username=settings.SMTP_USER,
        password=settings.SMTP_PASSWORD,
        use_tls=settings.SMTP_SSL,
        start_tls=settings.SMTP_TLS if not settings.SMTP_SSL else False,
    )


async def send_confirmation_email(to_email: str, token: str) -> None:
    """Send the account-confirmation email with the activation link."""
    confirm_url = f"{settings.APP_BASE_URL}/register/confirm/{token}"
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #5a3e1b;">Confirma tu cuenta en Truficultura</h2>
  <p>Hola,</p>
  <p>Gracias por registrarte. Pulsa el enlace siguiente para confirmar tu dirección de email y activar tu cuenta:</p>
  <p style="margin: 32px 0;">
    <a href="{confirm_url}"
       style="background: #5a3e1b; color: #fff; padding: 12px 24px;
              text-decoration: none; border-radius: 6px; font-weight: bold;">
      Confirmar cuenta
    </a>
  </p>
  <p>O copia esta URL en tu navegador:</p>
  <p style="word-break: break-all; color: #666;">{confirm_url}</p>
  <p style="color: #999; font-size: 0.85em;">Este enlace caduca en 24 horas. Si no solicitaste esta cuenta, ignora este mensaje.</p>
</body>
</html>
"""
    await send_email(to_email, "Confirma tu cuenta en Truficultura", html_body)


async def send_password_reset_email(to_email: str, token: str) -> None:
    """Send the password-reset email with the reset link."""
    reset_url = f"{settings.APP_BASE_URL}/reset-password/{token}"
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #5a3e1b;">Recuperación de contraseña — Truficultura</h2>
  <p>Hola,</p>
  <p>Hemos recibido una solicitud para restablecer la contraseña de tu cuenta. Pulsa el enlace siguiente para crear una nueva:</p>
  <p style="margin: 32px 0;">
    <a href="{reset_url}"
       style="background: #5a3e1b; color: #fff; padding: 12px 24px;
              text-decoration: none; border-radius: 6px; font-weight: bold;">
      Restablecer contraseña
    </a>
  </p>
  <p>O copia esta URL en tu navegador:</p>
  <p style="word-break: break-all; color: #666;">{reset_url}</p>
  <p style="color: #999; font-size: 0.85em;">Este enlace caduca en 1 hora. Si no solicitaste este cambio, ignora este mensaje.</p>
</body>
</html>
"""
    await send_email(to_email, "Recuperación de contraseña — Truficultura", html_body)

"""Async email sending.

Backend selection (priority order):
  1. Postmark HTTP API  — when POSTMARK_API_KEY is configured.
  2. SMTP (aiosmtplib)  — legacy fallback while SMTP_* vars remain configured.

If neither backend is configured, every send call is a no-op so the app
works normally in development without a mail server.
"""

from __future__ import annotations

import html
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib
import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_POSTMARK_API_URL = "https://api.postmarkapp.com/email"


async def _send_via_postmark(
    to: str, subject: str, html_body: str, from_addr: str
) -> None:
    """Send a single email through the Postmark HTTP API."""
    payload = {
        "From": from_addr,
        "To": to,
        "Subject": subject,
        "HtmlBody": html_body,
        "MessageStream": "outbound",
    }
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Postmark-Server-Token": settings.POSTMARK_API_KEY,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(_POSTMARK_API_URL, json=payload, headers=headers)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError:
            logger.error(
                "[email] Postmark rejected message to=%s from=%s status=%s body=%s",
                to,
                from_addr,
                response.status_code,
                response.text,
            )
            raise
    data = response.json()
    logger.info(
        "[email] Postmark delivered to=%s subject=%r message_id=%s",
        to,
        subject,
        data.get("MessageID", "?"),
    )


async def _send_via_smtp(to: str, subject: str, html_body: str) -> None:
    """Send via legacy SMTP (aiosmtplib)."""
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


async def send_email(to: str, subject: str, html_body: str) -> None:
    """Send an HTML email to *to*.

    Uses Postmark when configured; falls back to SMTP; silently skips when
    neither backend is ready.
    """
    if settings.postmark_configured:
        try:
            await _send_via_postmark(to, subject, html_body, settings.effective_from)
            return
        except Exception as exc:
            if settings.smtp_configured:
                logger.warning(
                    "[email] Postmark failed, falling back to SMTP for to=%s subject=%r: %s",
                    to,
                    subject,
                    exc,
                )
                await _send_via_smtp(to, subject, html_body)
                return
            raise

    if settings.smtp_configured:
        await _send_via_smtp(to, subject, html_body)
        return

    logger.info(
        "[email] No email backend configured — skipping send to %s: %s", to, subject
    )


async def send_confirmation_email(to_email: str, token: str) -> None:
    """Send the account-confirmation email with the activation link."""
    confirm_url = f"{settings.APP_BASE_URL}/register/confirm/{token}"
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #5a3e1b;">Confirma tu cuenta en Trufiq</h2>
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
    await send_email(to_email, "Confirma tu cuenta en Trufiq", html_body)


async def send_password_reset_email(to_email: str, token: str) -> None:
    """Send the password-reset email with the reset link."""
    reset_url = f"{settings.APP_BASE_URL}/reset-password/{token}"
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #5a3e1b;">Recuperación de contraseña — Trufiq</h2>
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
    await send_email(to_email, "Recuperación de contraseña — Trufiq", html_body)


async def send_lead_notification(
    name: str, email: str, message: str | None = None
) -> None:
    """Notifica al propietario de la app cuando un nuevo lead se registra en la landing."""
    contact_email = settings.CONTACT_EMAIL or settings.effective_from
    if not settings.email_configured:
        logger.warning(
            "[lead] Sin backend de email configurado — lead '%s' <%s> guardado en BD pero no se envió email.",
            name,
            email,
        )
        return

    # Escape user-supplied values to prevent HTML injection in the internal notification.
    safe_name = html.escape(name)
    safe_email = html.escape(email)
    safe_message = html.escape(message) if message else None

    leads_url = f"{settings.APP_BASE_URL}/admin/leads"
    message_row = (
        f"""
    <tr>
      <td style="padding: 8px; font-weight: 600; border-bottom: 1px solid #e5e0d8; width: 100px; vertical-align: top;">Mensaje</td>
      <td style="padding: 8px; border-bottom: 1px solid #e5e0d8; white-space: pre-wrap;">{safe_message}</td>
    </tr>"""
        if safe_message
        else ""
    )
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 540px; margin: 0 auto; padding: 24px; color: #2f261d;">
  <h2 style="font-family: Georgia, serif; color: #566b2f;">Nuevo interesado en Trufiq</h2>
  <table style="width:100%; border-collapse: collapse; margin-top: 1rem;">
    <tr>
      <td style="padding: 8px; font-weight: 600; border-bottom: 1px solid #e5e0d8; width: 100px;">Nombre</td>
      <td style="padding: 8px; border-bottom: 1px solid #e5e0d8;">{safe_name}</td>
    </tr>
    <tr>
      <td style="padding: 8px; font-weight: 600; border-bottom: 1px solid #e5e0d8;">Email</td>
      <td style="padding: 8px; border-bottom: 1px solid #e5e0d8;"><a href="mailto:{safe_email}">{safe_email}</a></td>
    </tr>    {message_row}  </table>
  <p style="margin-top: 1.5rem;">
    <a href="{leads_url}"
       style="background: #566b2f; color: #fff; padding: 10px 20px; border-radius: 8px;
              text-decoration: none; font-weight: 600;">
      Ver panel de leads
    </a>
  </p>
</body>
</html>
"""
    await send_email(
        contact_email, f"[Trufiq] Nuevo interesado: {safe_name}", html_body
    )


async def send_subscription_activated_email(
    to_email: str, ends_at: str | None = None
) -> None:
    """Notifica al usuario que su suscripción está activa."""
    ends_line = (
        f"<p>Tu acceso está activo hasta el <strong>{ends_at}</strong>.</p>"
        if ends_at
        else ""
    )
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #5a3e1b;">¡Suscripción activada en Trufiq!</h2>
  <p>Hola,</p>
  <p>Tu suscripción anual a Trufiq está activa. Ya tienes acceso completo a todas las funcionalidades.</p>
  {ends_line}
  <p style="margin: 32px 0;">
    <a href="{settings.APP_BASE_URL}"
       style="background: #5a3e1b; color: #fff; padding: 12px 24px;
              text-decoration: none; border-radius: 6px; font-weight: bold;">
      Ir a Trufiq
    </a>
  </p>
  <p style="color: #999; font-size: 0.85em;">Puedes gestionar tu suscripción en cualquier momento desde la sección de facturación.</p>
</body>
</html>
"""
    await send_email(to_email, "Tu suscripción a Trufiq está activa", html_body)


async def send_subscription_renewed_email(
    to_email: str, ends_at: str | None = None
) -> None:
    """Notifica al usuario que su suscripción se ha renovado correctamente."""
    ends_line = (
        f"<p>Tu acceso está renovado hasta el <strong>{ends_at}</strong>.</p>"
        if ends_at
        else ""
    )
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #5a3e1b;">Suscripción renovada — Trufiq</h2>
  <p>Hola,</p>
  <p>Tu suscripción anual a Trufiq se ha renovado correctamente.</p>
  {ends_line}
  <p style="color: #999; font-size: 0.85em;">Si no reconoces este cargo, contacta con nosotros en <a href="mailto:soporte@trufiq.app">soporte@trufiq.app</a>.</p>
</body>
</html>
"""
    await send_email(to_email, "Tu suscripción a Trufiq se ha renovado", html_body)


async def send_payment_failed_email(to_email: str) -> None:
    """Notifica al usuario que su pago ha fallado."""
    billing_url = f"{settings.APP_BASE_URL}/billing/subscribe"
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #b91c1c;">Problema con tu pago en Trufiq</h2>
  <p>Hola,</p>
  <p>No hemos podido procesar el pago de tu suscripción. Para mantener el acceso a Trufiq, actualiza tu método de pago.</p>
  <p style="margin: 32px 0;">
    <a href="{billing_url}"
       style="background: #b91c1c; color: #fff; padding: 12px 24px;
              text-decoration: none; border-radius: 6px; font-weight: bold;">
      Actualizar método de pago
    </a>
  </p>
  <p style="color: #999; font-size: 0.85em;">Si necesitas ayuda, escríbenos a <a href="mailto:soporte@trufiq.app">soporte@trufiq.app</a>.</p>
</body>
</html>
"""
    await send_email(to_email, "Problema con tu pago en Trufiq", html_body)


async def send_subscription_canceled_email(
    to_email: str, ends_at: str | None = None
) -> None:
    """Notifica al usuario que su suscripción ha sido cancelada."""
    ends_line = (
        f"<p>Mantendrás el acceso hasta el <strong>{ends_at}</strong>.</p>"
        if ends_at
        else ""
    )
    billing_url = f"{settings.APP_BASE_URL}/billing/subscribe"
    html_body = f"""
<!DOCTYPE html>
<html lang="es">
<body style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 24px; color: #333;">
  <h2 style="color: #5a3e1b;">Suscripción cancelada — Trufiq</h2>
  <p>Hola,</p>
  <p>Tu suscripción a Trufiq ha sido cancelada.</p>
  {ends_line}
  <p>Si cambias de opinión, puedes volver a suscribirte en cualquier momento:</p>
  <p style="margin: 32px 0;">
    <a href="{billing_url}"
       style="background: #5a3e1b; color: #fff; padding: 12px 24px;
              text-decoration: none; border-radius: 6px; font-weight: bold;">
      Reactivar suscripción
    </a>
  </p>
  <p style="color: #999; font-size: 0.85em;">Si tienes alguna duda, escríbenos a <a href="mailto:soporte@trufiq.app">soporte@trufiq.app</a>.</p>
</body>
</html>
"""
    await send_email(to_email, "Tu suscripción a Trufiq ha sido cancelada", html_body)

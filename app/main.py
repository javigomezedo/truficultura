from contextlib import asynccontextmanager
import binascii
import json
import logging

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, BadTimeSignature, SignatureExpired
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import (
    NotAuthenticatedException,
    NotAdminException,
    SubscriptionRequiredException,
    require_subscription,
)
from app.config import settings
from app.database import engine, get_db
from fastapi import Form
from app.i18n import set_locale, AVAILABLE_LOCALES
from app.jinja import templates
import app.models  # noqa: F401 - ensure models are registered
from app.models.user import User
from app.observability import (
    configure_logging,
    install_global_exception_hooks,
    metrics_middleware,
    render_metrics,
)
from app.routers import (
    admin,
    aemet_admin,
    assistant,
    auth,
    billing,
    charts,
    expenses,
    exports,
    harvests,
    imports,
    incomes,
    irrigation,
    kpis,
    lluvia,
    plot_analytics,
    plants,
    plot_events,
    plots,
    recurring_expenses,
    reports,
    scan,
    weather,
    wells,
)
from app.services.dashboard_service import build_dashboard_context

configure_logging(level=settings.LOG_LEVEL, json_logs=settings.LOG_JSON)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan hook for graceful async engine disposal."""
    install_global_exception_hooks(logger)
    yield
    await engine.dispose()


app = FastAPI(
    title="Trufiq",
    description="Gestión de explotación trufícola",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    https_only=settings.PRODUCTION,
    same_site="lax",
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Share the templates instance (with filters) across all routers
plots.templates = templates
expenses.templates = templates
incomes.templates = templates
reports.templates = templates
charts.templates = templates
imports.templates = templates
auth.templates = templates
irrigation.templates = templates
exports.templates = templates
harvests.templates = templates
plants.templates = templates
scan.templates = templates
wells.templates = templates
kpis.templates = templates
plot_events.templates = templates
plot_analytics.templates = templates
recurring_expenses.templates = templates
lluvia.templates = templates
weather.templates = templates
billing.templates = templates

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(assistant.router)
app.include_router(plots.router)
app.include_router(expenses.router)
app.include_router(incomes.router)
app.include_router(reports.router)
app.include_router(charts.router)
app.include_router(imports.router)
app.include_router(irrigation.router)
app.include_router(wells.router)
app.include_router(plot_events.router)
app.include_router(plot_analytics.router)
app.include_router(exports.router)
app.include_router(plants.router)
app.include_router(harvests.router)
app.include_router(scan.router)
app.include_router(kpis.router)
app.include_router(recurring_expenses.router)
app.include_router(lluvia.router)
app.include_router(weather.router)
app.include_router(aemet_admin.router)
app.include_router(billing.router)


@app.get("/landing", response_class=HTMLResponse, include_in_schema=False)
async def landing_page():
    """Serve the standalone landing page."""
    landing_path = "app/templates/landing_page.html"
    with open(landing_path, encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.post("/landing/contact", include_in_schema=False)
async def landing_contact(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    message: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    """Registra un lead desde la landing page y notifica al propietario."""
    import hashlib
    import re
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models.lead_capture import LeadCapture
    from app.services.email_service import send_lead_notification

    EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

    name = name.strip()
    email = email.strip().lower()
    message = message.strip()[:2000]  # Límite de caracteres por seguridad

    if not name or not EMAIL_RE.match(email):
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": False, "error": "Datos inválidos."}, status_code=422)

    # Deduplicación: mismo email en las últimas 24 h → devolver OK silencioso
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    existing = await db.execute(
        select(LeadCapture).where(
            LeadCapture.email == email, LeadCapture.created_at >= since
        )
    )
    if existing.scalars().first():
        from fastapi.responses import JSONResponse

        return JSONResponse({"ok": True})

    # Hash parcial de IP (RGPD)
    client_ip = request.client.host if request.client else ""
    ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16] if client_ip else None

    lead = LeadCapture(name=name, email=email, ip_hash=ip_hash, message=message or None)
    db.add(lead)
    await db.commit()

    # Notificación por email (silenciosa si SMTP no está configurado)
    try:
        await send_lead_notification(name=name, email=email, message=message or None)
    except Exception:
        logger.exception("Error enviando notificación de lead para <%s>", email)

    from fastapi.responses import JSONResponse

    return JSONResponse({"ok": True})


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
async def metrics(request: Request):
    if not settings.METRICS_ENABLED:
        raise HTTPException(status_code=404)

    if settings.METRICS_TOKEN:
        provided_token = request.headers.get("x-metrics-token")
        if provided_token != settings.METRICS_TOKEN:
            raise HTTPException(status_code=403, detail="Forbidden")

    return render_metrics()


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(NotAdminException)
async def not_admin_handler(request: Request, exc: NotAdminException):
    return RedirectResponse(url="/", status_code=303)


@app.exception_handler(SubscriptionRequiredException)
async def subscription_required_handler(
    request: Request, exc: SubscriptionRequiredException
):
    return RedirectResponse(url="/billing/subscribe", status_code=303)


@app.middleware("http")
async def locale_middleware(request: Request, call_next):
    """Set the per-request locale from session (falls back to Accept-Language, then default)."""
    session = request.scope.get("session") or {}
    locale = session.get("locale") or request.cookies.get("locale")
    if not locale or locale not in AVAILABLE_LOCALES:
        from app.i18n import get_locale_from_accept

        locale = get_locale_from_accept(request.headers.get("accept-language"))
    set_locale(locale)
    response = await call_next(request)
    return response


@app.middleware("http")
async def recover_invalid_session_cookie(request: Request, call_next):
    """Recover gracefully if a stale/corrupted signed session cookie is received.

    This can happen across deployments when a client keeps an old cookie that
    can no longer be decoded. Instead of returning a 500, clear the session
    cookie and force re-authentication.
    """
    try:
        return await call_next(request)
    except (
        BadSignature,
        BadTimeSignature,
        SignatureExpired,
        binascii.Error,
        json.JSONDecodeError,
        UnicodeDecodeError,
    ):
        if "session" not in request.cookies:
            raise
        response = RedirectResponse(url="/login", status_code=303)
        response.delete_cookie("session")
        return response


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    return await metrics_middleware(request, call_next, logger)


def _apply_locale_to_response(
    request: Request, response: RedirectResponse, selected_locale: str | None
) -> RedirectResponse:
    """Persist the chosen locale in session and cookie on a redirect response."""
    if selected_locale:
        request.session["locale"] = selected_locale
        response.set_cookie(
            "locale",
            selected_locale,
            max_age=365 * 24 * 60 * 60,  # 1 year – survives browser restarts
            samesite="lax",
        )
    return response


@app.get("/set-language", response_class=RedirectResponse)
async def set_language_get(
    request: Request,
    locale: str = "",
):
    """Persist the chosen locale via a simple GET link (used by the navbar dropdown)."""
    selected_locale = locale if locale in AVAILABLE_LOCALES else None
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=303)
    return _apply_locale_to_response(request, response, selected_locale)


@app.post("/set-language", response_class=RedirectResponse)
async def set_language(
    request: Request,
    locale: str = Form(...),
):
    """Persist the chosen locale in the session and redirect back (legacy POST form)."""
    selected_locale = locale if locale in AVAILABLE_LOCALES else None
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=303)
    return _apply_locale_to_response(request, response, selected_locale)


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    context = await build_dashboard_context(db, current_user.id)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            **context,
        },
    )

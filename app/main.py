from contextlib import asynccontextmanager
import binascii
import json

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from itsdangerous import BadSignature, BadTimeSignature, SignatureExpired
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NotAuthenticatedException, NotAdminException, require_user
from app.config import settings
from app.database import engine, get_db
from fastapi import Form
from app.i18n import set_locale, AVAILABLE_LOCALES
from app.jinja import templates
import app.models  # noqa: F401 - ensure models are registered
from app.models.user import User
from app.routers import (
    admin,
    assistant,
    auth,
    charts,
    expenses,
    exports,
    imports,
    incomes,
    irrigation,
    kpis,
    plants,
    plots,
    reports,
    scan,
    wells,
)
from app.services.dashboard_service import build_dashboard_context


@asynccontextmanager
async def lifespan(app: FastAPI):
    """App lifespan hook for graceful async engine disposal."""
    yield
    await engine.dispose()


app = FastAPI(
    title="Truficultura",
    description="Gestión de explotación trufícola",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
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
plants.templates = templates
scan.templates = templates
wells.templates = templates
kpis.templates = templates

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
app.include_router(exports.router)
app.include_router(plants.router)
app.include_router(scan.router)
app.include_router(kpis.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(NotAdminException)
async def not_admin_handler(request: Request, exc: NotAdminException):
    return RedirectResponse(url="/", status_code=303)


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


@app.post("/set-language", response_class=RedirectResponse)
async def set_language(
    request: Request,
    locale: str = Form(...),
):
    """Persist the chosen locale in the session and redirect back."""
    selected_locale = locale if locale in AVAILABLE_LOCALES else None
    if selected_locale:
        request.session["locale"] = selected_locale
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer, status_code=303)
    if selected_locale:
        response.set_cookie("locale", selected_locale, samesite="lax")
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
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

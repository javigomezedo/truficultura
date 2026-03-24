from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.sessions import SessionMiddleware

from app.auth import NotAuthenticatedException, NotAdminException, require_user
from app.config import settings
from app.database import Base, engine, get_db
from app.i18n import get_locale, load_translations
from app.jinja import templates
from app.models import User, Plot, Expense, Income  # noqa: F401 - ensure models are registered
from app.routers import auth, charts, expenses, imports, incomes, plots, reports, admin
from app.services.dashboard_service import build_dashboard_context


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create all database tables on startup if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


app = FastAPI(
    title="Truficultura",
    description="Gestión de explotación trufícola",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Install default (Spanish) translations at startup
_default_translations = load_translations("es")
templates.env.install_gettext_translations(_default_translations, newstyle=True)

# Share the templates instance (with filters) across all routers
plots.templates = templates
expenses.templates = templates
incomes.templates = templates
reports.templates = templates
charts.templates = templates
imports.templates = templates
auth.templates = templates

# Include routers
app.include_router(auth.router)
app.include_router(admin.router)
app.include_router(plots.router)
app.include_router(expenses.router)
app.include_router(incomes.router)
app.include_router(reports.router)
app.include_router(charts.router)
app.include_router(imports.router)


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request: Request, exc: NotAuthenticatedException):
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(NotAdminException)
async def not_admin_handler(request: Request, exc: NotAdminException):
    return RedirectResponse(url="/", status_code=303)


@app.middleware("http")
async def i18n_middleware(request: Request, call_next):
    """Detect browser language and install appropriate translations."""
    accept_language = request.headers.get("accept-language")
    locale = get_locale(accept_language)
    translations = load_translations(locale)
    templates.env.install_gettext_translations(translations, newstyle=True)
    response = await call_next(request)
    return response


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    context = await build_dashboard_context(db, current_user.id)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            **context,
        },
    )

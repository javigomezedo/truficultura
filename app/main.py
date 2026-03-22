from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, engine, get_db
from app.i18n import get_locale, load_translations
from app.models import Plot, Expense, Income  # noqa: F401 - ensure models are registered
from app.routers import plots, expenses, incomes, reports, charts, imports
from app.services.dashboard_service import build_dashboard_context
from app.utils import campaign_label


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

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["campaign_label"] = campaign_label
templates.env.add_extension("jinja2.ext.i18n")

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

# Include routers
app.include_router(plots.router)
app.include_router(expenses.router)
app.include_router(incomes.router)
app.include_router(reports.router)
app.include_router(charts.router)
app.include_router(imports.router)


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
):
    context = await build_dashboard_context(db)

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            **context,
        },
    )

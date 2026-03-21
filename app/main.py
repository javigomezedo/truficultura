from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Base, engine, get_db
from app.models import Parcela, Gasto, Ingreso  # noqa: F401 - ensure models are registered
from app.routers import parcelas, gastos, ingresos, reportes, graficas
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

# Share the templates instance (with filters) across all routers
parcelas.templates = templates
gastos.templates = templates
ingresos.templates = templates
reportes.templates = templates
graficas.templates = templates

# Include routers
app.include_router(parcelas.router)
app.include_router(gastos.router)
app.include_router(ingresos.router)
app.include_router(reportes.router)
app.include_router(graficas.router)


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

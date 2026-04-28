from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.models.user import User
from app.services.weather_service import get_weather_contexts

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tiempo", tags=["tiempo"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def weather_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
) -> HTMLResponse:
    """Página completa de tiempo meteorológico en tiempo real."""
    weather_list = await get_weather_contexts(db, current_user.id)
    return templates.TemplateResponse(
        request,
        "tiempo/index.html",
        {"request": request, "weather_list": weather_list},
    )


@router.get("/widget", response_class=JSONResponse)
async def weather_widget(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
) -> JSONResponse:
    """Endpoint JSON para el widget asíncrono del dashboard (todos los municipios)."""
    weather_list = await get_weather_contexts(db, current_user.id)

    def _fmt_num(val: float | None, decimals: int = 1) -> str | None:
        if val is None:
            return None
        return f"{val:.{decimals}f}".replace(".", ",")

    # Si hay error global (no_municipio, no_api_key) → viene como lista con un error
    if len(weather_list) == 1 and not weather_list[0].get("available"):
        return JSONResponse({"available": False, "error": weather_list[0].get("error")})

    items = []
    for ctx in weather_list:
        if not ctx.get("available"):
            continue
        items.append(
            {
                "display_name": ctx.get("display_name"),
                "source": ctx.get("source"),
                "temperature": _fmt_num(ctx.get("temperature"), 1),
                "humidity": _fmt_num(ctx.get("humidity"), 0),
                "precipitation_today": _fmt_num(ctx.get("precipitation_today"), 1),
                "rain_month": _fmt_num(ctx.get("rain_month"), 0),
                "updated_ago_label": ctx.get("updated_ago_label"),
                "freshness": ctx.get("freshness"),
                "tomorrow_sky": ctx.get("tomorrow_sky"),
                "tomorrow_t_max": ctx.get("tomorrow_t_max"),
                "tomorrow_t_min": ctx.get("tomorrow_t_min"),
                "tomorrow_prob_prec": ctx.get("tomorrow_prob_prec"),
            }
        )

    return JSONResponse({"available": True, "municipios": items})

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.jinja import templates
from app.models.user import User
from app.services.plots_service import list_plots

router = APIRouter(prefix="/maps", tags=["maps"])


@router.get("/", response_class=HTMLResponse)
async def maps_index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    plots = await list_plots(db, current_user.active_tenant_id)
    return templates.TemplateResponse(
        request,
        "maps/index.html",
        {"request": request, "plots": plots},
    )

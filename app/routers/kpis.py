from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.models.user import User
from app.services.kpi_service import build_kpi_context

router = APIRouter(prefix="/kpis", tags=["kpis"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def kpis_index(
    request: Request,
    campaign: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    context = await build_kpi_context(
        db, user_id=current_user.id, selected_campaign=campaign
    )

    return templates.TemplateResponse(
        request,
        "kpis/index.html",
        {
            "request": request,
            **context,
        },
    )

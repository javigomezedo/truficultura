from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.models.user import User
from app.services.charts_service import build_charts_context

router = APIRouter(prefix="/charts", tags=["charts"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def charts_index(
    request: Request,
    campaign: Optional[int] = None,
    plot_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    context = await build_charts_context(
        db, campaign=campaign, plot_id=plot_id, user_id=current_user.id
    )

    return templates.TemplateResponse(
        request,
        "graficas/index.html",
        {
            "request": request,
            **context,
        },
    )

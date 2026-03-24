from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.models.user import User
from app.services.reports_service import build_profitability_context

router = APIRouter(prefix="/reports", tags=["reports"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/profitability", response_class=HTMLResponse)
async def profitability(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    context = await build_profitability_context(db, current_user.id)

    return templates.TemplateResponse(
        "reportes/rentabilidad.html",
        {
            "request": request,
            **context,
        },
    )

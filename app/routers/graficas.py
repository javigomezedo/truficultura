from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.graficas_service import build_graficas_context

router = APIRouter(prefix="/graficas", tags=["graficas"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def graficas_index(
    request: Request,
    campaign: Optional[int] = None,
    bancal_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    context = await build_graficas_context(db, campaign=campaign, bancal_id=bancal_id)

    # ------------------------------------------------------------------ #
    # Render
    # ------------------------------------------------------------------ #
    return templates.TemplateResponse(
        "graficas/index.html",
        {
            "request": request,
            **context,
        },
    )

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.reportes_service import build_rentabilidad_context

router = APIRouter(prefix="/reportes", tags=["reportes"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/rentabilidad", response_class=HTMLResponse)
async def rentabilidad(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    context = await build_rentabilidad_context(db)

    return templates.TemplateResponse(
        "reportes/rentabilidad.html",
        {
            "request": request,
            **context,
        },
    )

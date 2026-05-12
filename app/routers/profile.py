from __future__ import annotations

from typing import Optional
from urllib.parse import quote_plus

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.i18n import _
from app.jinja import templates
from app.models.user import User
from app.services.profile_service import update_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("/", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "profile/edit.html",
        {"request": request, "current_user": current_user},
    )


@router.post("/", response_class=HTMLResponse)
async def profile_update(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    username: str = Form(...),
    comunidad_regantes: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    result = await update_profile(
        db=db,
        user=current_user,
        first_name=first_name,
        last_name=last_name,
        username=username,
        comunidad_regantes=comunidad_regantes == "on",
    )

    if isinstance(result, str):
        return templates.TemplateResponse(
            request,
            "profile/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "error": result,
            },
            status_code=400,
        )

    # Refresh session with updated values
    request.session["first_name"] = result.first_name
    request.session["last_name"] = result.last_name
    request.session["username"] = result.username

    return RedirectResponse(
        url=f"/?msg={quote_plus(_('Perfil actualizado correctamente'))}",
        status_code=303,
    )

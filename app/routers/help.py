from __future__ import annotations
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi import APIRouter, Depends, Form, Request
from datetime import UTC, datetime
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from app.auth import require_user
from app.database import get_db
from app.help_videos import SECTION_LABELS, available_videos
from app.jinja import templates
from app.models.user import User

"""Páginas de ayuda y glosario.

Acceso público (no requiere login) para que los enlaces de los `help_hint`
sean linkables desde cualquier sitio, incluyendo correos o landing.

Excepción: `POST /ayuda/onboarding-guide/step` requiere sesión y
actualiza el estado de onboarding del usuario.
"""


router = APIRouter(prefix="/ayuda", tags=["ayuda"])

"""Páginas de ayuda y glosario.

Acceso público (no requiere login) para que los enlaces de los `help_hint`
sean linkables desde cualquier sitio, incluyendo correos o landing.

Excepción: `POST /ayuda/onboarding-guide/step` requiere sesión y
actualiza el estado de onboarding del usuario.
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def help_index(request: Request):
    return templates.TemplateResponse(
        request,
        "ayuda/index.html",
        {"videos": available_videos(), "section_labels": SECTION_LABELS},
    )


@router.get("/glosario", response_class=HTMLResponse, include_in_schema=False)
async def glossary(request: Request):
    return templates.TemplateResponse(request, "ayuda/glosario.html")


@router.get("/videos", response_class=HTMLResponse, include_in_schema=False)
async def videos_index(request: Request):
    """Lista los vídeos cuyos ficheros están en disco, agrupados por sección."""
    videos = available_videos()
    grouped: dict[str, list] = {}
    for v in videos:
        grouped.setdefault(v.section, []).append(v)
    return templates.TemplateResponse(
        request,
        "ayuda/videos.html",
        {"grouped_videos": grouped, "section_labels": SECTION_LABELS},
    )


_VALID_STEPS = {
    "welcome",
    "first_plot",
    "first_plants",
    "first_expense",
    "done",
    "skipped",
}


@router.post("/onboarding-guide/step", include_in_schema=False)
async def update_onboarding_step(
    request: Request,
    step: str = Form(...),
    user: User = Depends(require_user),
    db: AsyncSession = Depends(get_db),
):
    """Persiste el paso actual del onboarding guiado del usuario.

    Acepta los valores definidos en ``_VALID_STEPS``. Cuando el paso es
    ``done`` o ``skipped``, sella ``onboarding_completed_at`` para que el
    modal de bienvenida no vuelva a aparecer.
    """
    if step not in _VALID_STEPS:
        return JSONResponse({"ok": False, "error": "invalid_step"}, status_code=400)

    values: dict[str, object] = {"onboarding_step": step}
    if step in ("done", "skipped"):
        values["onboarding_completed_at"] = datetime.now(UTC)

    await db.execute(update(User).where(User.id == user.id).values(**values))
    await db.commit()

    # Mantener la sesión coherente sin esperar al siguiente request.
    request.session["onboarding_step"] = step

    return JSONResponse({"ok": True, "step": step})

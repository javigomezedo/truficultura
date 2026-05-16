from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, require_subscription
from app.config import settings
from app.database import get_db
from app.models.incident import INCIDENT_CATEGORIES, INCIDENT_SEVERITIES, Incident
from app.models.user import User
from app.services import incidents_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/incidents", tags=["incidents"])
templates = Jinja2Templates(directory="app/templates")

_ATTACHMENT_ALLOWED_MIME = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "application/pdf",
    }
)
_MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5 MB


# ---------------------------------------------------------------------------
# Rutas de usuario
# ---------------------------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
async def list_incidents(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    incidents = await incidents_service.get_incidents_by_tenant(
        db, current_user.active_tenant_id
    )
    return templates.TemplateResponse(
        request,
        "incidents/list.html",
        {
            "request": request,
            "incidents": incidents,
            "msg": request.query_params.get("msg"),
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_incident_form(
    request: Request,
    current_user: User = Depends(require_subscription),
):
    return templates.TemplateResponse(
        request,
        "incidents/new.html",
        {
            "request": request,
            "categories": INCIDENT_CATEGORIES,
            "severities": INCIDENT_SEVERITIES,
        },
    )


@router.post("/")
async def create_incident(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    category: str = Form(...),
    severity: str = Form(...),
    attachment: Optional[UploadFile] = File(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    # Validar categoría y severidad
    if category not in INCIDENT_CATEGORIES:
        category = "otro"
    if severity not in INCIDENT_SEVERITIES:
        severity = "media"

    attachment_filename = None
    attachment_data = None
    attachment_content_type = None

    if attachment and attachment.filename:
        content_type = attachment.content_type or ""
        if content_type not in _ATTACHMENT_ALLOWED_MIME:
            return templates.TemplateResponse(
                request,
                "incidents/new.html",
                {
                    "request": request,
                    "categories": INCIDENT_CATEGORIES,
                    "severities": INCIDENT_SEVERITIES,
                    "error": "Tipo de fichero no permitido. Usa JPG, PNG, GIF, WEBP o PDF.",
                    "form": {
                        "title": title,
                        "description": description,
                        "category": category,
                        "severity": severity,
                    },
                },
                status_code=422,
            )
        raw = await attachment.read()
        if len(raw) > _MAX_ATTACHMENT_BYTES:
            return templates.TemplateResponse(
                request,
                "incidents/new.html",
                {
                    "request": request,
                    "categories": INCIDENT_CATEGORIES,
                    "severities": INCIDENT_SEVERITIES,
                    "error": "El fichero supera el límite de 5 MB.",
                    "form": {
                        "title": title,
                        "description": description,
                        "category": category,
                        "severity": severity,
                    },
                },
                status_code=422,
            )
        attachment_filename = attachment.filename
        attachment_data = raw
        attachment_content_type = content_type

    incident = await incidents_service.create_incident(
        db=db,
        tenant_id=current_user.active_tenant_id,
        user_id=current_user.id,
        title=title.strip(),
        description=description.strip(),
        category=category,
        severity=severity,
        attachment_filename=attachment_filename,
        attachment_data=attachment_data,
        attachment_content_type=attachment_content_type,
    )

    # Notificar al admin por email
    try:
        from app.services.email_service import send_incident_notification
        await send_incident_notification(incident=incident, user=current_user)
    except Exception:
        logger.exception("Error enviando notificación de incidencia #%s", incident.id)

    from urllib.parse import quote_plus
    msg = quote_plus("Incidencia registrada correctamente. Te notificaremos cuando sea resuelta.")
    return RedirectResponse(url=f"/incidents/?msg={msg}", status_code=303)


@router.get("/{incident_id}", response_class=HTMLResponse)
async def detail_incident(
    incident_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    incident = await incidents_service.get_incident_by_id(db, incident_id)
    if incident is None or incident.tenant_id != current_user.active_tenant_id:
        return RedirectResponse(url="/incidents/", status_code=303)
    return templates.TemplateResponse(
        request,
        "incidents/detail.html",
        {"request": request, "incident": incident},
    )


@router.get("/{incident_id}/attachment")
async def download_attachment(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    incident = await incidents_service.get_incident_by_id(db, incident_id)
    if (
        incident is None
        or incident.tenant_id != current_user.active_tenant_id
        or not incident.attachment_data
    ):
        from fastapi.responses import Response
        return Response(status_code=404)

    content_type = incident.attachment_content_type or "application/octet-stream"
    if content_type not in _ATTACHMENT_ALLOWED_MIME:
        from fastapi.responses import Response
        return Response(status_code=403)

    filename = incident.attachment_filename or f"adjunto_{incident_id}"
    return StreamingResponse(
        BytesIO(incident.attachment_data),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Rutas de admin (dentro de /incidents pero protegidas por require_admin)
# ---------------------------------------------------------------------------


@router.get("/admin/list", response_class=HTMLResponse)
async def admin_list_incidents(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
    resolved: Optional[str] = Query(default=None),
    tenant_id: Optional[int] = Query(default=None),
    category: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
):
    resolved_filter: Optional[bool] = None
    if resolved == "true":
        resolved_filter = True
    elif resolved == "false":
        resolved_filter = False

    incidents = await incidents_service.get_all_incidents_admin(
        db,
        resolved=resolved_filter,
        tenant_id=tenant_id,
        category=category or None,
        severity=severity or None,
    )
    return templates.TemplateResponse(
        request,
        "admin/incidents.html",
        {
            "request": request,
            "incidents": incidents,
            "current_user": current_user,
            "filter_resolved": resolved or "",
            "filter_tenant_id": tenant_id,
            "filter_category": category or "",
            "filter_severity": severity or "",
            "categories": INCIDENT_CATEGORIES,
            "severities": INCIDENT_SEVERITIES,
        },
    )


@router.get("/admin/{incident_id}", response_class=HTMLResponse)
async def admin_detail_incident(
    incident_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    incident = await incidents_service.get_incident_by_id(db, incident_id)
    if incident is None:
        return RedirectResponse(url="/incidents/admin/list", status_code=303)
    return templates.TemplateResponse(
        request,
        "incidents/detail.html",
        {"request": request, "incident": incident, "admin_view": True},
    )


@router.get("/admin/{incident_id}/attachment")
async def admin_download_attachment(
    incident_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    incident = await incidents_service.get_incident_by_id(db, incident_id)
    if incident is None or not incident.attachment_data:
        from fastapi.responses import Response
        return Response(status_code=404)

    content_type = incident.attachment_content_type or "application/octet-stream"
    if content_type not in _ATTACHMENT_ALLOWED_MIME:
        from fastapi.responses import Response
        return Response(status_code=403)

    filename = incident.attachment_filename or f"adjunto_{incident_id}"
    return StreamingResponse(
        BytesIO(incident.attachment_data),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/admin/{incident_id}/resolve")
async def admin_resolve_incident(
    incident_id: int,
    request: Request,
    admin_response: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    incident = await incidents_service.get_incident_by_id(db, incident_id)
    if incident is None:
        return RedirectResponse(url="/incidents/admin/list", status_code=303)

    incident = await incidents_service.resolve_incident(
        db, incident, admin_response.strip()
    )

    # Notificar al usuario por email
    if incident.user and incident.user.email:
        try:
            from app.services.email_service import send_incident_resolved_email
            await send_incident_resolved_email(incident=incident)
        except Exception:
            logger.exception(
                "Error enviando email de resolución de incidencia #%s", incident.id
            )

    return RedirectResponse(
        url=f"/incidents/admin/{incident_id}?resolved=1", status_code=303
    )

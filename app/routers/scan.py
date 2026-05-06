from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, require_subscription
from app.config import settings
from app.database import get_db
from app.models.plant import PlantStatus
from app.models.user import User
from app.services import plants_service, truffle_events_service

router = APIRouter(tags=["scan"])
templates = Jinja2Templates(directory="app/templates")

_signer = URLSafeSerializer(settings.SECRET_KEY, salt="plant-qr")


def sign_plant_token(plant_id: int) -> str:
    """Return a URL-safe signed token encoding the plant id."""
    return _signer.dumps({"pid": plant_id})


def verify_plant_token(token: str) -> Optional[int]:
    """Return plant_id if token is valid, otherwise None."""
    try:
        data = _signer.loads(token)
        return int(data["pid"])
    except (BadSignature, KeyError, TypeError, ValueError):
        return None


@router.get("/scan/{token}", response_class=HTMLResponse)
async def scan_qr(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    """Entry point for QR code scans.

    If the user is not authenticated, redirect to login with the scan URL
    stored so the flow can be completed after a successful login.
    """
    plant_id = verify_plant_token(token)
    if plant_id is None:
        return templates.TemplateResponse(
            request,
            "scan/invalid.html",
            {"request": request},
            status_code=400,
        )

    if current_user is None:
        request.session["pending_scan"] = token
        return RedirectResponse(f"/login?next=/scan/{token}", status_code=303)

    # User is authenticated — get the plant and show quantity confirmation
    plant = await plants_service.get_plant(db, plant_id, current_user.active_tenant_id)
    if plant is None:
        return templates.TemplateResponse(
            request,
            "scan/invalid.html",
            {"request": request},
            status_code=404,
        )

    if plant.status == PlantStatus.muerta:
        return templates.TemplateResponse(
            request,
            "scan/invalid.html",
            {"request": request, "reason": "dead"},
            status_code=409,
        )

    return templates.TemplateResponse(
        request,
        "scan/confirm.html",
        {
            "request": request,
            "plant": plant,
        },
    )


@router.post("/scan/{token}", response_class=HTMLResponse)
async def scan_qr_submit(
    request: Request,
    token: str,
    estimated_weight_grams: float = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user),
):
    plant_id = verify_plant_token(token)
    if plant_id is None:
        return templates.TemplateResponse(
            request,
            "scan/invalid.html",
            {"request": request},
            status_code=400,
        )

    if current_user is None:
        request.session["pending_scan"] = token
        return RedirectResponse(f"/login?next=/scan/{token}", status_code=303)

    plant = await plants_service.get_plant(db, plant_id, current_user.active_tenant_id)
    if plant is None:
        return templates.TemplateResponse(
            request,
            "scan/invalid.html",
            {"request": request},
            status_code=404,
        )

    if plant.status == PlantStatus.muerta:
        return templates.TemplateResponse(
            request,
            "scan/invalid.html",
            {"request": request, "reason": "dead"},
            status_code=409,
        )

    estimated_weight = max(1.0, min(float(estimated_weight_grams), 5000.0))
    last_event = await truffle_events_service.create_event(
        db,
        plant_id=plant.id,
        plot_id=plant.plot_id,
        tenant_id=current_user.active_tenant_id,
        acting_user_id=current_user.id,
        estimated_weight_grams=estimated_weight,
        source="qr",
        dedupe_window_seconds=0,
    )

    request.session.pop("pending_scan", None)

    return templates.TemplateResponse(
        request,
        "scan/success.html",
        {
            "request": request,
            "plant": plant,
            "event": last_event,
            "estimated_weight_grams": estimated_weight,
        },
    )

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import settings
from app.database import get_db
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

    if not request.session.get("user_id"):
        request.session["pending_scan"] = token
        return RedirectResponse(f"/login?next=/scan/{token}", status_code=303)

    # User is authenticated — get the plant and register the event
    plant = await plants_service.get_plant(db, plant_id, request.session["user_id"])
    if plant is None:
        return templates.TemplateResponse(
            request,
            "scan/invalid.html",
            {"request": request},
            status_code=404,
        )

    event = await truffle_events_service.create_event(
        db,
        plant_id=plant.id,
        plot_id=plant.plot_id,
        user_id=request.session["user_id"],
        source="qr",
    )

    request.session.pop("pending_scan", None)

    return templates.TemplateResponse(
        request,
        "scan/success.html",
        {
            "request": request,
            "plant": plant,
            "event": event,
            "undo_url": f"/plots/{plant.plot_id}/plants/{plant.id}/undo",
        },
    )

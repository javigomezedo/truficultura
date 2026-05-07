"""Router: quality analytics — harvest vs. sales cross-reference by truffle quality."""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_subscription
from app.database import get_db
from app.models.user import User
from app.services.quality_analytics_service import get_quality_analytics_context

router = APIRouter(prefix="/quality-analytics", tags=["quality_analytics"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def quality_analytics(
    request: Request,
    campaign: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_subscription),
):
    ctx = await get_quality_analytics_context(
        db,
        tenant_id=current_user.active_tenant_id,
        selected_campaign=campaign,
    )
    ctx["request"] = request
    ctx["qualities_json"] = json.dumps(ctx["qualities"])
    ctx["harvest_kg_json"] = json.dumps(
        [ctx["harvest_kg"].get(q, 0) for q in ctx["qualities"]]
    )
    ctx["sales_kg_json"] = json.dumps(
        [ctx["sales_kg"].get(q, 0) for q in ctx["qualities"]]
    )
    ctx["sales_eur_json"] = json.dumps(
        [ctx["sales_eur"].get(q, 0) for q in ctx["qualities"]]
    )
    ctx["sales_eur_per_kg_json"] = json.dumps(
        [ctx["sales_eur_per_kg"].get(q, 0) for q in ctx["qualities"]]
    )
    return templates.TemplateResponse(request, "analytics/quality.html", ctx)

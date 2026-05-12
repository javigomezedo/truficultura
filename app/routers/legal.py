from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter(tags=["legal"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/privacidad", response_class=HTMLResponse, include_in_schema=False)
async def privacy_policy(request: Request):
    return templates.TemplateResponse(request, "legal/privacidad.html")


@router.get("/aviso-legal", response_class=HTMLResponse, include_in_schema=False)
async def legal_notice(request: Request):
    return templates.TemplateResponse(request, "legal/aviso_legal.html")

"""Páginas de ayuda y glosario.

Acceso público (no requiere login) para que los enlaces de los `help_hint`
sean linkables desde cualquier sitio, incluyendo correos o landing.
"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.jinja import templates

router = APIRouter(prefix="/ayuda", tags=["ayuda"])


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def help_index(request: Request):
    return templates.TemplateResponse(request, "ayuda/index.html")


@router.get("/glosario", response_class=HTMLResponse, include_in_schema=False)
async def glossary(request: Request):
    return templates.TemplateResponse(request, "ayuda/glosario.html")

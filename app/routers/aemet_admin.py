from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth import require_user
from app.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/aemet", tags=["admin-aemet"])



@router.get("/stations", response_class=JSONResponse)
async def aemet_stations_proxy(
    api_key: Optional[str] = None,
    current_user: User = Depends(require_user),
):
    """Proxy para obtener el listado de estaciones AEMET evitando CORS."""
    meta_url = "https://opendata.aemet.es/opendata/api/valores/climatologicos/inventarioestaciones/todasestaciones"
    headers = {"accept": "application/json"}
    params: dict[str, str] = {}
    effective_api_key = (
        api_key.strip() if api_key and api_key.strip() else settings.AEMET_API_KEY
    )
    if effective_api_key:
        params["api_key"] = effective_api_key

    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            meta_resp = None
            last_exc = None
            for attempt in range(3):
                try:
                    meta_resp = await client.get(
                        meta_url, headers=headers, params=params
                    )
                    last_exc = None
                    break
                except httpx.RequestError as exc:
                    logger.warning("AEMET stations intento %d: %s", attempt + 1, exc)
                    last_exc = exc
            if last_exc is not None:
                return JSONResponse(
                    {"error": f"Error de red al conectar con AEMET: {last_exc}"},
                    status_code=502,
                )
            try:
                meta = meta_resp.json()
            except Exception as exc:
                return JSONResponse(
                    {"error": "No se pudo interpretar la respuesta de AEMET."},
                    status_code=502,
                )
            if meta_resp.status_code != 200 or "datos" not in meta:
                return JSONResponse(
                    {
                        "error": meta.get(
                            "descripcion",
                            "No se pudo obtener el enlace de datos de estaciones.",
                        )
                    },
                    status_code=502,
                )
            data_url = meta["datos"]
            data_resp = None
            last_exc = None
            for attempt in range(3):
                try:
                    data_resp = await client.get(data_url)
                    last_exc = None
                    break
                except httpx.RequestError as exc:
                    logger.warning("AEMET datos intento %d: %s", attempt + 1, exc)
                    last_exc = exc
            if last_exc is not None:
                return JSONResponse(
                    {"error": f"Error de red al descargar estaciones: {last_exc}"},
                    status_code=502,
                )
            if data_resp.status_code != 200:
                return JSONResponse(
                    {"error": f"AEMET devolvió HTTP {data_resp.status_code}."},
                    status_code=502,
                )
            try:
                data = json.loads(data_resp.content.decode("latin-1"))
            except Exception:
                return JSONResponse(
                    {"error": "No se pudo interpretar el listado de estaciones."},
                    status_code=502,
                )
            return JSONResponse(data)
    except Exception as exc:
        return JSONResponse({"error": f"Error inesperado: {exc}"}, status_code=500)



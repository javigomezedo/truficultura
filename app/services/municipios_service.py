"""Búsqueda de municipios españoles y su código INE mediante Nominatim (OSM).

El código INE se obtiene del campo ``extratags["ref:ine"]`` que OpenStreetMap
mantiene para todos los municipios de España.

Uso:
    municipios = await search_municipios("Sarrion")
    # → [{"name": "Sarrión", "ine_code": "44216", "province": "Gúdar-Javalambre", ...}]
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_TIMEOUT = 15.0
# Nominatim ToS: identificar la aplicación con un User-Agent descriptivo.
_USER_AGENT = "trufiq-app/1.0 (truffle-farm management; non-commercial)"

HttpGetJson = Callable[[str, dict, float], Any]


async def _default_get_json(url: str, params: dict, timeout: float) -> Any:
    """Realiza GET y devuelve payload JSON parseado."""
    async with httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _extract_ine_code(result: dict) -> Optional[str]:
    """Extrae el código INE municipal (5 dígitos) de un resultado Nominatim.

    Nominatim almacena el código en ``ine:municipio`` (p. ej. "44210")
    o, alternativamente, en ``ref:ine`` como código censal largo
    (p. ej. "44210000000"), del que tomamos los 5 primeros dígitos.
    """
    extratags = result.get("extratags") or {}

    # Campo preferido: exactamente 5 dígitos
    for key in ("ine:municipio", "ref:ine:municipio"):
        code = extratags.get(key)
        if code and len(str(code)) == 5 and str(code).isdigit():
            return str(code)

    # Fallback: ref:ine puede ser el código censal largo (11 dígitos),
    # los primeros 5 son el código municipal.
    ref = extratags.get("ref:ine")
    if ref and str(ref).isdigit() and len(str(ref)) >= 5:
        return str(ref)[:5]

    return None


def _extract_name(result: dict, fallback: str) -> str:
    """Extrae el nombre legible del municipio de un resultado Nominatim."""
    address = result.get("address") or {}
    return (
        address.get("municipality")
        or address.get("city")
        or address.get("town")
        or address.get("village")
        or result.get("name")
        or fallback
    )


def _extract_province(result: dict) -> str:
    """Extrae la comarca / provincia de un resultado Nominatim."""
    address = result.get("address") or {}
    return (
        address.get("county")
        or address.get("state_district")
        or address.get("state")
        or ""
    )


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------


async def search_municipios(
    query: str,
    *,
    limit: int = 8,
    http_get_json: Optional[HttpGetJson] = None,
) -> list[dict]:
    """Busca municipios españoles por nombre y devuelve su código INE.

    Consulta Nominatim (OpenStreetMap) con ``featuretype=city`` para acotar
    los resultados a entidades de tipo municipio. Solo devuelve entradas
    que tengan un código INE válido (5 dígitos).

    Args:
        query: texto a buscar (nombre del municipio).
        limit: número máximo de resultados a devolver.
        http_get_json: función HTTP inyectable para tests.

    Returns:
        Lista de dicts ``{name, ine_code, province, display_name}``,
        ordenada por relevancia de Nominatim.
    """
    if not query or len(query.strip()) < 2:
        return []

    get_fn = http_get_json or _default_get_json
    params = {
        "q": query.strip(),
        "countrycodes": "es",
        "format": "jsonv2",
        "addressdetails": "1",
        "extratags": "1",
        # Pedimos el doble para compensar los que no tienen ref:ine
        "limit": str(limit * 2),
    }

    try:
        results = await get_fn(NOMINATIM_URL, params, _NOMINATIM_TIMEOUT)
    except Exception as exc:
        logger.warning("Nominatim search failed for %r: %s", query, exc)
        return []

    if not isinstance(results, list):
        return []

    out: list[dict] = []
    for r in results:
        ine_code = _extract_ine_code(r)
        if not ine_code:
            continue
        out.append(
            {
                "name": _extract_name(r, query),
                "ine_code": ine_code,
                "province": _extract_province(r),
                "display_name": r.get("display_name", ""),
            }
        )
        if len(out) >= limit:
            break

    return out

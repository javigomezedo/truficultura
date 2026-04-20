from __future__ import annotations

import httpx


_SIGPAC_URL = (
    "https://sigpac.mapa.es/fega/serviciosvisorsigpac/layerinfo/recinto"
    "/{provincia},{municipio},{agregado},{zona},{poligono},{parcela},{recinto}/"
)


class SigpacError(Exception):
    """Raised when the SIGPAC API returns an unexpected response."""


def _format_fecha_vuelo(raw: int | str | None) -> str:
    """Convert 202408 → '08/2024'."""
    if raw is None:
        return ""
    s = str(raw)
    if len(s) == 6:
        return f"{s[4:]}/{s[:4]}"
    return s


def _format_iso_date(raw: str | None) -> str:
    """Convert '2023-11-05T23:00:00.000Z' → '05/11/2023'."""
    if not raw:
        return ""
    try:
        # take the date part only
        date_part = raw[:10]  # 'YYYY-MM-DD'
        y, m, d = date_part.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return raw


async def fetch_sigpac_data(
    provincia: str,
    municipio: str,
    poligono: str,
    parcela: str,
    recinto: str = "1",
    *,
    agregado: str = "0",
    zona: str = "0",
) -> dict:
    """Call the SIGPAC public API and return a structured dict.

    Returns:
        {
          "autocomplete": {"cadastral_ref": str, "area_ha": float},
          "details": { ... all transformed fields for the modal ... }
        }

    Raises:
        SigpacError: if the API is unreachable or returns unexpected data.
    """
    url = _SIGPAC_URL.format(
        provincia=provincia,
        municipio=municipio,
        agregado=agregado,
        zona=zona,
        poligono=poligono,
        parcela=parcela,
        recinto=recinto,
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPStatusError as exc:
        raise SigpacError(
            f"SIGPAC respondió con estado {exc.response.status_code}"
        ) from exc
    except httpx.RequestError as exc:
        raise SigpacError(f"No se pudo conectar con SIGPAC: {exc}") from exc

    parcela_info = data.get("parcelaInfo")
    if not parcela_info:
        raise SigpacError("La respuesta de SIGPAC no contiene información de parcela")

    # ── autocomplete fields ────────────────────────────────────────────────
    cadastral_ref: str = parcela_info.get("referencia_cat", "")
    raw_surface = parcela_info.get("dn_surface") or 0.0
    area_ha = round(raw_surface / 10000, 4)

    # ── details for the modal ─────────────────────────────────────────────
    convergencia = data.get("convergencia", {})
    vuelo = data.get("vuelo", {})

    recintos_raw: list[dict] = data.get("query") or []
    recintos = [
        {
            "recinto": r.get("recinto"),
            "superficie_ha": round((r.get("dn_surface") or 0.0) / 10000, 4),
            "pendiente_pct": round((r.get("pendiente_media") or 0) / 10, 2),
            "altitud_m": r.get("altitud"),
            "uso_sigpac": r.get("uso_sigpac", ""),
            "coef_regadio": r.get("coef_regadio"),
            "incidencias": r.get("incidencias", ""),
            "region": r.get("region"),
        }
        for r in recintos_raw
    ]

    # Collect incidencias_texto from all recintos (may differ per recinto)
    incidencias_texto: list[str] = []
    for r in recintos_raw:
        for txt in r.get("inctexto") or []:
            if txt not in incidencias_texto:
                incidencias_texto.append(txt)

    details = {
        "vigencia": data.get("vigencia", ""),
        "fecha_vuelo": _format_fecha_vuelo(vuelo.get("fecha_vuelo")),
        "fecha_cartografia": _format_iso_date(convergencia.get("cat_fechaultimaconv")),
        "parcela": {
            "provincia": parcela_info.get("provincia", ""),
            "municipio": parcela_info.get("municipio", ""),
            "agregado": parcela_info.get("agregado"),
            "zona": parcela_info.get("zona"),
            "poligono": parcela_info.get("poligono"),
            "parcela": parcela_info.get("parcela"),
            "superficie_ha": area_ha,
            "referencia_cat": cadastral_ref,
        },
        "recintos": recintos,
        "incidencias_texto": incidencias_texto,
    }

    return {
        "autocomplete": {
            "cadastral_ref": cadastral_ref,
            "area_ha": area_ha,
        },
        "details": details,
    }

"""Unit tests for sigpac_service.fetch_sigpac_data."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sigpac_service import SigpacError, fetch_sigpac_data

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_RESPONSE = {
    "id": ["44", "223", "0", "0", "12", "309", "1"],
    "isRecin": True,
    "vigencia": "15/12/2025",
    "query": [
        {
            "recinto": 1,
            "dn_surface": 2694.55403146227,
            "pendiente_media": 42,
            "uso_sigpac": "TA - TIERRAS ARABLES",
            "admisibilidad": None,
            "superficie_admisible": None,
            "coef_regadio": 0,
            "incidencias": "12,199",
            "region": 1,
            "altitud": 998,
            "inctexto": [
                "12 - Contiene otros usos sin subdividir",
                "199 - Recinto inactivo",
            ],
        }
    ],
    "parcelaInfo": {
        "provincia": "44 - TERUEL",
        "municipio": "223 - SARRION",
        "agregado": 0,
        "zona": 0,
        "poligono": 12,
        "parcela": 309,
        "dn_surface": 2694.55403146227,
        "referencia_cat": "44223A012003090000FZ",
    },
    "convergencia": {"cat_fechaultimaconv": "2023-11-05T23:00:00.000Z"},
    "vuelo": {"fecha_vuelo": 202408},
    "arboles": [],
}


def _mock_client(json_data: dict, status_code: int = 200):
    """Return a mock httpx.AsyncClient whose get() returns json_data."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    if status_code >= 400:
        import httpx

        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status = MagicMock()

    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_sigpac_data_success_autocomplete():
    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(SAMPLE_RESPONSE)
        result = await fetch_sigpac_data("44", "223", "12", "309", "1")

    assert result["autocomplete"]["cadastral_ref"] == "44223A012003090000FZ"
    assert result["autocomplete"]["area_ha"] == pytest.approx(0.2695, rel=1e-3)


@pytest.mark.asyncio
async def test_fetch_sigpac_data_success_details_vigencia():
    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(SAMPLE_RESPONSE)
        result = await fetch_sigpac_data("44", "223", "12", "309", "1")

    assert result["details"]["vigencia"] == "15/12/2025"


@pytest.mark.asyncio
async def test_fetch_sigpac_data_fecha_vuelo_format():
    """202408 should be converted to '08/2024'."""
    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(SAMPLE_RESPONSE)
        result = await fetch_sigpac_data("44", "223", "12", "309", "1")

    assert result["details"]["fecha_vuelo"] == "08/2024"


@pytest.mark.asyncio
async def test_fetch_sigpac_data_fecha_cartografia_format():
    """ISO timestamp should be converted to 'dd/mm/yyyy'."""
    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(SAMPLE_RESPONSE)
        result = await fetch_sigpac_data("44", "223", "12", "309", "1")

    assert result["details"]["fecha_cartografia"] == "05/11/2023"


@pytest.mark.asyncio
async def test_fetch_sigpac_data_pendiente_conversion():
    """pendiente_media=42 (tenths of %) → 4.2 %"""
    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(SAMPLE_RESPONSE)
        result = await fetch_sigpac_data("44", "223", "12", "309", "1")

    assert result["details"]["recintos"][0]["pendiente_pct"] == pytest.approx(4.2)


@pytest.mark.asyncio
async def test_fetch_sigpac_data_incidencias_texto():
    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client(SAMPLE_RESPONSE)
        result = await fetch_sigpac_data("44", "223", "12", "309", "1")

    texts = result["details"]["incidencias_texto"]
    assert "12 - Contiene otros usos sin subdividir" in texts
    assert "199 - Recinto inactivo" in texts


@pytest.mark.asyncio
async def test_fetch_sigpac_data_http_error_raises_sigpac_error():
    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client({}, status_code=404)
        with pytest.raises(SigpacError, match="404"):
            await fetch_sigpac_data("44", "223", "12", "309", "1")


@pytest.mark.asyncio
async def test_fetch_sigpac_data_missing_parcela_info_raises():
    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value = _mock_client({"query": []})
        with pytest.raises(SigpacError, match="parcela"):
            await fetch_sigpac_data("44", "223", "12", "309", "1")


@pytest.mark.asyncio
async def test_fetch_sigpac_data_request_error_raises_sigpac_error():
    import httpx

    with patch("app.services.sigpac_service.httpx.AsyncClient") as mock_cls:
        client = MagicMock()
        client.get = AsyncMock(
            side_effect=httpx.RequestError("connection refused", request=MagicMock())
        )
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = client

        with pytest.raises(SigpacError, match="conectar"):
            await fetch_sigpac_data("44", "223", "12", "309", "1")

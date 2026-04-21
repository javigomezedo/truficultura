from __future__ import annotations

import pytest

from app.services.municipios_service import (
    _extract_ine_code,
    _extract_name,
    _extract_province,
    search_municipios,
)


# ---------------------------------------------------------------------------
# Helpers internos
# ---------------------------------------------------------------------------


def _nominatim_result(
    *,
    ine_municipio: str = "44210",
    name: str = "Sarrión",
    county: str = "Gúdar-Javalambre",
    display_name: str = "Sarrión, Gúdar-Javalambre, Teruel, Aragón, España",
) -> dict:
    """Fixture que replica la estructura real que devuelve Nominatim para España."""
    return {
        "display_name": display_name,
        "name": name,
        "extratags": {
            "ine:municipio": ine_municipio,
            "ref:ine": ine_municipio + "000000",  # código censal largo
        },
        "address": {
            "village": name,  # Nominatim usa village/town, no municipality
            "county": county,
            "province": "Teruel",
            "state": "Aragón",
            "country": "España",
        },
    }


def test_extract_ine_code_from_ine_municipio() -> None:
    """Campo ine:municipio (5 dígitos exactos) — caso habitual."""
    result = _nominatim_result(ine_municipio="44210")
    assert _extract_ine_code(result) == "44210"


def test_extract_ine_code_from_long_ref_ine() -> None:
    """ref:ine largo (11 dígitos) — se extraen los 5 primeros."""
    result = {"extratags": {"ref:ine": "44210000000"}}
    assert _extract_ine_code(result) == "44210"


def test_extract_ine_code_missing_returns_none() -> None:
    result = {"extratags": {}}
    assert _extract_ine_code(result) is None


def test_extract_ine_code_non_numeric_returns_none() -> None:
    result = {"extratags": {"ref:ine": "442AB000000"}}
    assert _extract_ine_code(result) is None


def test_extract_name_prefers_village() -> None:
    """Nominatim devuelve village en lugar de municipality para pueblos."""
    result = _nominatim_result(name="Sarrión")
    assert _extract_name(result, "fallback") == "Sarrión"


def test_extract_name_falls_back_to_result_name() -> None:
    result = {"name": "Albentosa", "address": {}}
    assert _extract_name(result, "fallback") == "Albentosa"


def test_extract_province_prefers_county() -> None:
    result = _nominatim_result(county="Gúdar-Javalambre")
    assert _extract_province(result) == "Gúdar-Javalambre"


# ---------------------------------------------------------------------------
# search_municipios
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_municipios_returns_ine_entries() -> None:
    fake_response = [
        _nominatim_result(ine_municipio="44210", name="Sarrión"),
        _nominatim_result(
            ine_municipio="44014", name="Albentosa", county="Gúdar-Javalambre"
        ),
    ]

    async def fake_get(url: str, params: dict, timeout: float) -> list:
        assert "sarrion" in params["q"].lower() or "sarri" in params["q"].lower()
        assert params["countrycodes"] == "es"
        return fake_response

    results = await search_municipios("Sarrion", http_get_json=fake_get)

    assert len(results) == 2
    assert results[0]["ine_code"] == "44210"
    assert results[0]["name"] == "Sarrión"
    assert results[0]["province"] == "Gúdar-Javalambre"


@pytest.mark.asyncio
async def test_search_municipios_filters_results_without_ine() -> None:
    """Resultados sin código INE se omiten."""
    fake_response = [
        {"display_name": "Sin código", "name": "X", "extratags": {}, "address": {}},
        _nominatim_result(ine_municipio="44210", name="Sarrión"),
    ]

    async def fake_get(url: str, params: dict, timeout: float) -> list:
        return fake_response

    results = await search_municipios("Sarrion", http_get_json=fake_get)

    assert len(results) == 1
    assert results[0]["ine_code"] == "44210"


@pytest.mark.asyncio
async def test_search_municipios_short_query_returns_empty() -> None:
    called = []

    async def fake_get(url: str, params: dict, timeout: float) -> list:
        called.append(True)
        return []

    result = await search_municipios("a", http_get_json=fake_get)

    assert result == []
    assert not called  # no debe llamar a la API


@pytest.mark.asyncio
async def test_search_municipios_http_error_returns_empty() -> None:
    async def fake_get(url: str, params: dict, timeout: float) -> list:
        raise ConnectionError("timeout")

    result = await search_municipios("Sarrion", http_get_json=fake_get)
    assert result == []


@pytest.mark.asyncio
async def test_search_municipios_respects_limit() -> None:
    fake_response = [
        _nominatim_result(ine_municipio=f"440{i:02d}", name=f"Pueblo{i}")
        for i in range(10)
    ]

    async def fake_get(url: str, params: dict, timeout: float) -> list:
        return fake_response

    results = await search_municipios("Pueblo", limit=3, http_get_json=fake_get)
    assert len(results) == 3

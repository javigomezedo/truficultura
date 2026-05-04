from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.rainfall import RainfallRecord
from app.services.ibericam_service import (
    fetch_ibericam_sitemap_slugs,
    find_ibericam_slug_for_municipio,
    import_ibericam_rainfall,
    parse_ibericam_response,
    scrape_ibericam_stations,
    upsert_ibericam_rainfall,
)
from tests.conftest import result


# ---------------------------------------------------------------------------
# parse_ibericam_response
# ---------------------------------------------------------------------------


def test_parse_ibericam_response_returns_date_and_mm() -> None:
    payload = [
        {"labels": "2026-04-01", "input": "0.0"},
        {"labels": "2026-04-02", "input": "3.4"},
        {"labels": "2026-04-03", "input": "12,5"},  # coma como separador decimal
    ]
    rows = parse_ibericam_response(payload)
    assert len(rows) == 3
    assert rows[0] == (datetime.date(2026, 4, 1), 0.0)
    assert rows[1] == (datetime.date(2026, 4, 2), pytest.approx(3.4))
    assert rows[2] == (datetime.date(2026, 4, 3), pytest.approx(12.5))


def test_parse_ibericam_response_filters_invalid_dates() -> None:
    payload = [
        {"labels": "not-a-date", "input": "1.0"},
        {"labels": "2026-04-05", "input": "2.0"},
    ]
    rows = parse_ibericam_response(payload)
    assert len(rows) == 1
    assert rows[0][0] == datetime.date(2026, 4, 5)


def test_parse_ibericam_response_negative_becomes_zero() -> None:
    payload = [{"labels": "2026-04-01", "input": "-5.0"}]
    rows = parse_ibericam_response(payload)
    assert rows[0][1] == 0.0


def test_parse_ibericam_response_null_input_is_zero() -> None:
    payload = [{"labels": "2026-04-01", "input": None}]
    rows = parse_ibericam_response(payload)
    assert rows[0][1] == 0.0


def test_parse_ibericam_response_non_list_returns_empty() -> None:
    assert parse_ibericam_response(None) == []
    assert parse_ibericam_response({"labels": "2026-04-01", "input": "1.0"}) == []


# ---------------------------------------------------------------------------
# upsert_ibericam_rainfall — crear registros nuevos
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upsert_ibericam_rainfall_creates_new_records() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))  # sin existentes
    db.add = MagicMock()
    db.flush = AsyncMock()

    records = [
        (datetime.date(2026, 4, 1), 0.0),
        (datetime.date(2026, 4, 2), 5.2),
    ]
    stats = await upsert_ibericam_rainfall(db, municipio_cod="44216", records=records)

    assert stats["created"] == 2
    assert stats["updated"] == 0
    assert stats["total"] == 2
    assert db.add.call_count == 2
    db.flush.assert_called_once()

    # Verificar que los objetos creados son globales (user_id=None)
    added: RainfallRecord = db.add.call_args_list[0].args[0]
    assert added.tenant_id is None
    assert added.municipio_cod == "44216"
    assert added.source == "ibericam"
    assert added.plot_id is None
    assert added.date == datetime.date(2026, 4, 1)
    assert added.precipitation_mm == pytest.approx(0.0)


@pytest.mark.asyncio
async def test_upsert_ibericam_rainfall_updates_existing_records() -> None:
    existing = RainfallRecord()
    existing.date = datetime.date(2026, 4, 1)
    existing.precipitation_mm = 1.0

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([existing]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    records = [(datetime.date(2026, 4, 1), 9.9)]
    stats = await upsert_ibericam_rainfall(db, municipio_cod="44216", records=records)

    assert stats["created"] == 0
    assert stats["updated"] == 1
    assert stats["total"] == 1
    db.add.assert_not_called()
    assert existing.precipitation_mm == pytest.approx(9.9)


@pytest.mark.asyncio
async def test_upsert_ibericam_rainfall_empty_input_returns_zeros() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.flush = AsyncMock()

    stats = await upsert_ibericam_rainfall(db, municipio_cod="44216", records=[])

    assert stats == {"created": 0, "updated": 0, "total": 0}
    db.execute.assert_not_called()
    db.flush.assert_not_called()


# ---------------------------------------------------------------------------
# import_ibericam_rainfall — pipeline completo
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_ibericam_rainfall_calls_pipeline() -> None:
    """Verifica el pipeline completo: fetch → parse → upsert."""
    fake_payload = [
        {"labels": "2026-03-01", "input": "0.0"},
        {"labels": "2026-03-05", "input": "14.4"},
    ]

    async def fake_post(url: str, body: dict, timeout: float) -> list:
        assert "station" in body
        assert body["station"] == "sarrion"
        assert body.get("month") == "03"
        assert body.get("year") == "2026"
        return fake_payload

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))  # sin existentes
    db.add = MagicMock()
    db.flush = AsyncMock()

    stats = await import_ibericam_rainfall(
        db,
        station_slug="sarrion",
        municipio_cod="44216",
        year=2026,
        month=3,
        http_post_json=fake_post,
    )

    assert stats["created"] == 2
    assert stats["total"] == 2


@pytest.mark.asyncio
async def test_import_ibericam_rainfall_date_range_iterates_months() -> None:
    """Con date_from/date_to itera mes a mes y filtra al rango."""
    calls: list[dict] = []

    async def fake_post(url: str, body: dict, timeout: float) -> list:
        calls.append(dict(body))
        if body.get("month") == "03":
            return [
                {"labels": "2026-03-15", "input": "5.0"},
                {"labels": "2026-03-31", "input": "2.0"},
            ]
        if body.get("month") == "04":
            return [
                {"labels": "2026-04-01", "input": "3.0"},
                {"labels": "2026-04-30", "input": "1.0"},  # fuera del rango date_to
            ]
        return []

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    stats = await import_ibericam_rainfall(
        db,
        station_slug="sarrion",
        municipio_cod="44216",
        date_from=datetime.date(2026, 3, 15),
        date_to=datetime.date(2026, 4, 10),
        http_post_json=fake_post,
    )

    # Debe haber llamado a marzo y abril
    assert len(calls) == 2
    assert any(c.get("month") == "03" for c in calls)
    assert any(c.get("month") == "04" for c in calls)
    # 2026-03-15, 2026-03-31, 2026-04-01 están en el rango; 2026-04-30 queda fuera
    assert stats["created"] == 3
    assert stats["total"] == 3


# ---------------------------------------------------------------------------
# scrape_ibericam_stations
# ---------------------------------------------------------------------------

_FAKE_SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset>
  <url><loc>https://ibericam.com/lugar_webcam_el_tiempo/sarrion/</loc></url>
  <url><loc>https://ibericam.com/lugar_webcam_el_tiempo/albentosa/</loc></url>
  <url><loc>https://ibericam.com/lugar_webcam_el_tiempo/aragon/</loc></url>
  <url><loc>https://ibericam.com/lugar_webcam_el_tiempo/categoria/</loc></url>
  <url><loc>https://ibericam.com/lugar_webcam_el_tiempo/gudar/</loc></url>
  <url><loc>https://ibericam.com/lugar_webcam_el_tiempo/pueblo/</loc></url>
</urlset>"""

_FAKE_RAIN_DATA = [
    {"labels": "2026-04-01", "input": "0.0"},
    {"labels": "2026-04-15", "input": "5.0"},
]


@pytest.mark.asyncio
async def test_scrape_ibericam_stations_returns_verified_stations() -> None:
    """El scraper filtra categorías y sólo devuelve slugs con datos reales."""
    calls: list[str] = []

    async def fake_get(url: str, timeout: float) -> str:
        return _FAKE_SITEMAP

    async def fake_post(url: str, body: dict, timeout: float) -> list:
        slug = body.get("station", "")
        calls.append(slug)
        # Solo sarrion y gudar devuelven datos; albentosa devuelve vacío
        if slug in ("sarrion", "gudar"):
            return _FAKE_RAIN_DATA
        return []

    stations = await scrape_ibericam_stations(
        http_get_text=fake_get,
        http_post_json=fake_post,
    )

    slugs_found = [s["slug"] for s in stations]
    assert "sarrion" in slugs_found
    assert "gudar" in slugs_found
    # albentosa devuelve vacío en el probe pero está en IBERICAM_SLUG_TO_MUNICIPIO → aparece como fallback
    assert "albentosa" in slugs_found
    albentosa_entry = next(s for s in stations if s["slug"] == "albentosa")
    assert albentosa_entry["num_records"] == 0
    # Categorías filtradas antes de sondar
    assert "aragon" not in calls
    assert "categoria" not in calls
    assert "pueblo" not in calls


@pytest.mark.asyncio
async def test_scrape_ibericam_stations_station_fields() -> None:
    """Cada estación incluye slug, name, last_date y num_records."""

    async def fake_get(url: str, timeout: float) -> str:
        return "<urlset><url><loc>https://ibericam.com/lugar_webcam_el_tiempo/sarrion/</loc></url></urlset>"

    async def fake_post(url: str, body: dict, timeout: float) -> list:
        return _FAKE_RAIN_DATA

    stations = await scrape_ibericam_stations(
        http_get_text=fake_get,
        http_post_json=fake_post,
    )
    # sarrion fue verificado por probe + los demás slugs conocidos se añaden como fallback
    slugs_found = [s["slug"] for s in stations]
    assert "sarrion" in slugs_found
    s = next(st for st in stations if st["slug"] == "sarrion")
    assert s["name"] == "Sarrion"
    assert s["last_date"] == "2026-04-15"
    assert s["num_records"] == 2


@pytest.mark.asyncio
async def test_scrape_ibericam_stations_empty_sitemap() -> None:
    """Si el sitemap no contiene slugs conocidos, devuelve lista vacía."""

    async def fake_get(url: str, timeout: float) -> str:
        return "<urlset></urlset>"

    async def fake_post(url: str, body: dict, timeout: float) -> list:
        return []

    stations = await scrape_ibericam_stations(
        http_get_text=fake_get,
        http_post_json=fake_post,
    )
    # Aunque el sitemap esté vacío, los slugs conocidos de IBERICAM_SLUG_TO_MUNICIPIO
    # siempre se incluyen como fallback con num_records=0.
    from app.services.ibericam_service import IBERICAM_SLUG_TO_MUNICIPIO

    assert len(stations) == len(IBERICAM_SLUG_TO_MUNICIPIO)
    assert all(s["num_records"] == 0 for s in stations)


@pytest.mark.asyncio
async def test_scrape_ibericam_stations_probe_error_skips_station() -> None:
    """Si el sondeo de una estación lanza excepción, se omite sin romper."""

    async def fake_get(url: str, timeout: float) -> str:
        return "<urlset><url><loc>https://ibericam.com/lugar_webcam_el_tiempo/sarrion/</loc></url></urlset>"

    async def fake_post(url: str, body: dict, timeout: float) -> list:
        raise RuntimeError("timeout")

    stations = await scrape_ibericam_stations(
        http_get_text=fake_get,
        http_post_json=fake_post,
    )
    # sarrion está en IBERICAM_SLUG_TO_MUNICIPIO → aparece como fallback aunque el probe falle
    slugs_found = [s["slug"] for s in stations]
    assert "sarrion" in slugs_found
    sarrion_entry = next(s for s in stations if s["slug"] == "sarrion")
    assert sarrion_entry["num_records"] == 0
    assert sarrion_entry["last_date"] is None


# ---------------------------------------------------------------------------
# fetch_ibericam_sitemap_slugs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fetch_ibericam_sitemap_slugs_returns_slugs() -> None:
    xml = (
        "<urlset>"
        "<url><loc>https://ibericam.com/lugar_webcam_el_tiempo/mora-de-rubielos/</loc></url>"
        "<url><loc>https://ibericam.com/lugar_webcam_el_tiempo/sarrion/</loc></url>"
        "</urlset>"
    )

    async def fake_get(url: str, timeout: float) -> str:
        return xml

    slugs = await fetch_ibericam_sitemap_slugs(http_get_text=fake_get)
    assert "mora-de-rubielos" in slugs
    assert "sarrion" in slugs


@pytest.mark.asyncio
async def test_fetch_ibericam_sitemap_slugs_filters_non_station() -> None:
    from app.services.ibericam_service import _NON_STATION_SLUGS

    non_station = next(iter(_NON_STATION_SLUGS))
    xml = (
        "<urlset>"
        f"<url><loc>https://ibericam.com/lugar_webcam_el_tiempo/{non_station}/</loc></url>"
        "<url><loc>https://ibericam.com/lugar_webcam_el_tiempo/sarrion/</loc></url>"
        "</urlset>"
    )

    async def fake_get(url: str, timeout: float) -> str:
        return xml

    slugs = await fetch_ibericam_sitemap_slugs(http_get_text=fake_get)
    assert non_station not in slugs
    assert "sarrion" in slugs


# ---------------------------------------------------------------------------
# find_ibericam_slug_for_municipio
# ---------------------------------------------------------------------------


def test_find_ibericam_slug_for_municipio_found() -> None:
    slugs = {"mora-de-rubielos", "sarrion", "alcala-de-la-selva"}
    assert (
        find_ibericam_slug_for_municipio(slugs, "Mora de Rubielos")
        == "mora-de-rubielos"
    )


def test_find_ibericam_slug_for_municipio_with_accent() -> None:
    slugs = {"sarrion", "alcala-de-la-selva"}
    assert find_ibericam_slug_for_municipio(slugs, "Sarrión") == "sarrion"


def test_find_ibericam_slug_for_municipio_not_found() -> None:
    slugs = {"sarrion", "alcala-de-la-selva"}
    assert find_ibericam_slug_for_municipio(slugs, "Teruel") is None


def test_find_ibericam_slug_for_municipio_strips_comma_suffix() -> None:
    slugs = {"cabra-de-mora"}
    assert (
        find_ibericam_slug_for_municipio(slugs, "Cabra de Mora, pedanía")
        == "cabra-de-mora"
    )


@pytest.mark.asyncio
async def test_fetch_ibericam_sitemap_slugs_empty_xml() -> None:
    """Sitemap sin URLs devuelve conjunto vacío."""

    async def fake_get(url: str, timeout: float) -> str:
        return "<urlset></urlset>"

    slugs = await fetch_ibericam_sitemap_slugs(http_get_text=fake_get)
    assert slugs == set()

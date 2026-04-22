from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.rainfall import RainfallRecord
from app.services.ibericam_service import (
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
    stats = await upsert_ibericam_rainfall(db, user_id=1, municipio_cod="44216", records=records)

    assert stats["created"] == 2
    assert stats["updated"] == 0
    assert stats["total"] == 2
    assert db.add.call_count == 2
    db.flush.assert_called_once()

    # Verificar que los objetos creados tienen los campos correctos
    added: RainfallRecord = db.add.call_args_list[0].args[0]
    assert added.user_id == 1
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
    stats = await upsert_ibericam_rainfall(db, user_id=1, municipio_cod="44216", records=records)

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

    stats = await upsert_ibericam_rainfall(db, user_id=1, municipio_cod="44216", records=[])

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
        user_id=1,
        station_slug="sarrion",
        municipio_cod="44216",
        year=2026,
        month=3,
        http_post_json=fake_post,
    )

    assert stats["created"] == 2
    assert stats["total"] == 2


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

    # Sólo slugs no filtrados y con datos reales
    slugs_found = [s["slug"] for s in stations]
    assert "sarrion" in slugs_found
    assert "gudar" in slugs_found
    assert "albentosa" not in slugs_found  # devolvió vacío → no verificado
    # Categorías filtradas antes de sondar
    assert "aragon" not in calls
    assert "categoria" not in calls
    assert "pueblo" not in calls


@pytest.mark.asyncio
async def test_scrape_ibericam_stations_station_fields() -> None:
    """Cada estación incluye slug, name, last_date y num_records."""
    async def fake_get(url: str, timeout: float) -> str:
        return '<urlset><url><loc>https://ibericam.com/lugar_webcam_el_tiempo/sarrion/</loc></url></urlset>'

    async def fake_post(url: str, body: dict, timeout: float) -> list:
        return _FAKE_RAIN_DATA

    stations = await scrape_ibericam_stations(
        http_get_text=fake_get,
        http_post_json=fake_post,
    )
    assert len(stations) == 1
    s = stations[0]
    assert s["slug"] == "sarrion"
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
    assert stations == []


@pytest.mark.asyncio
async def test_scrape_ibericam_stations_probe_error_skips_station() -> None:
    """Si el sondeo de una estación lanza excepción, se omite sin romper."""
    async def fake_get(url: str, timeout: float) -> str:
        return '<urlset><url><loc>https://ibericam.com/lugar_webcam_el_tiempo/sarrion/</loc></url></urlset>'

    async def fake_post(url: str, body: dict, timeout: float) -> list:
        raise RuntimeError("timeout")

    stations = await scrape_ibericam_stations(
        http_get_text=fake_get,
        http_post_json=fake_post,
    )
    assert stations == []


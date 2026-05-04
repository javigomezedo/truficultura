"""Unit tests for app.services.admin_service."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest


# ── helpers ───────────────────────────────────────────────────────────────────


class _FakeResult:
    def __init__(self, rows) -> None:
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Async session that pops from a pre-set list of results per execute()."""

    def __init__(self, *results) -> None:
        self._results = list(results)
        self._idx = 0

    async def execute(self, *args, **kwargs):
        r = self._results[self._idx]
        self._idx += 1
        return r


def _row(**kw):
    return SimpleNamespace(**kw)


# ── _normalize_municipio_cod ──────────────────────────────────────────────────


def test_normalize_with_provincia_short_municipio() -> None:
    from app.services.admin_service import _normalize_municipio_cod

    assert _normalize_municipio_cod("10", "5") == "10005"


def test_normalize_with_provincia_three_digit_municipio() -> None:
    from app.services.admin_service import _normalize_municipio_cod

    assert _normalize_municipio_cod("28", "079") == "28079"


def test_normalize_without_provincia_returns_as_is() -> None:
    from app.services.admin_service import _normalize_municipio_cod

    assert _normalize_municipio_cod(None, "28079") == "28079"


def test_normalize_long_municipio_without_prefix() -> None:
    from app.services.admin_service import _normalize_municipio_cod

    # municipio_cod already 5 digits → len > 3 so returned unchanged even with provincia
    assert _normalize_municipio_cod("10", "10005") == "10005"


# ── _build_geo_name_map ───────────────────────────────────────────────────────


def test_build_geo_name_map_returns_dict() -> None:
    from app.services.admin_service import _build_geo_name_map

    # Clear cache so this call actually executes the function body
    _build_geo_name_map.cache_clear()
    result = _build_geo_name_map()
    assert isinstance(result, dict)


# ── get_admin_rainfall_overview ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_admin_rainfall_overview_empty_plots() -> None:
    """When no plots have a municipio_cod the function returns []."""
    from app.services.admin_service import get_admin_rainfall_overview

    # First execute: plots by municipio → empty
    db = _FakeDB(_FakeResult([]))
    result = await get_admin_rainfall_overview(db)  # type: ignore[arg-type]
    assert result == []


@pytest.mark.asyncio
async def test_get_admin_rainfall_overview_with_data() -> None:
    from app.services.admin_service import get_admin_rainfall_overview

    # Execute 1: plots by municipio
    plots_result = _FakeResult(
        [
            _row(provincia_cod="10", municipio_cod="005", num_plots=3),
        ]
    )
    # Execute 2: AEMET date ranges
    d_since = datetime.date(2024, 1, 1)
    d_until = datetime.date(2024, 12, 31)
    aemet_result = _FakeResult(
        [
            _row(municipio_cod="10005", desde=d_since, hasta=d_until),
        ]
    )
    # Execute 3: Ibericam date ranges
    ibericam_result = _FakeResult([])
    # Execute 4: municipality names
    names_result = _FakeResult(
        [
            _row(municipio_cod="10005", municipio_name="Plasencia"),
        ]
    )

    db = _FakeDB(plots_result, aemet_result, ibericam_result, names_result)
    overview = await get_admin_rainfall_overview(db)  # type: ignore[arg-type]

    assert len(overview) == 1
    entry = overview[0]
    assert entry["municipio_cod"] == "10005"
    assert entry["municipio_name"] == "Plasencia"
    assert entry["num_plots"] == 3
    assert entry["aemet_desde"] == d_since
    assert entry["aemet_hasta"] == d_until
    assert entry["ibericam_desde"] is None
    assert entry["ibericam_hasta"] is None


@pytest.mark.asyncio
async def test_get_admin_rainfall_overview_falls_back_to_cod_when_no_name() -> None:
    from app.services.admin_service import get_admin_rainfall_overview

    plots_result = _FakeResult(
        [
            _row(provincia_cod=None, municipio_cod="99999", num_plots=1),
        ]
    )
    aemet_result = _FakeResult([])
    ibericam_result = _FakeResult([])
    names_result = _FakeResult([])  # no names → fallback to code

    db = _FakeDB(plots_result, aemet_result, ibericam_result, names_result)
    overview = await get_admin_rainfall_overview(db)  # type: ignore[arg-type]

    assert len(overview) == 1
    # municipio_name falls back to the code itself when nothing else is found
    assert overview[0]["municipio_name"] == "99999"


@pytest.mark.asyncio
async def test_get_admin_rainfall_overview_aggregates_same_municipio() -> None:
    """Two plots with different raw codes that normalize to the same municipality."""
    from app.services.admin_service import get_admin_rainfall_overview

    # Two rows that normalize to the same "10005"
    plots_result = _FakeResult(
        [
            _row(provincia_cod="10", municipio_cod="005", num_plots=2),
            _row(provincia_cod="10", municipio_cod="005", num_plots=1),
        ]
    )
    aemet_result = _FakeResult([])
    ibericam_result = _FakeResult([])
    names_result = _FakeResult([])

    db = _FakeDB(plots_result, aemet_result, ibericam_result, names_result)
    overview = await get_admin_rainfall_overview(db)  # type: ignore[arg-type]

    assert len(overview) == 1
    assert overview[0]["num_plots"] == 3  # 2 + 1 aggregated

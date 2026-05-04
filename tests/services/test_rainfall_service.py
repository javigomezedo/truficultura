from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.rainfall import RainfallRecord
from app.schemas.rainfall import RainfallCreate, RainfallUpdate
from app.services.rainfall_service import (
    create_rainfall_record,
    delete_rainfall_record,
    get_rainfall_calendar_context,
    get_rainfall_for_plot_on_date,
    get_rainfall_list_context,
    get_rainfall_record,
    list_rainfall_records,
    update_rainfall_record,
    _build_calendar_months,
)
from tests.conftest import result


def _make_record(**kwargs) -> RainfallRecord:
    defaults = dict(
        id=1,
        tenant_id=1,
        plot_id=1,
        municipio_cod=None,
        date=datetime.date(2025, 11, 10),
        precipitation_mm=12.5,
        source="manual",
        notes=None,
    )
    defaults.update(kwargs)
    return RainfallRecord(**defaults)


# ---------------------------------------------------------------------------
# get_rainfall_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rainfall_record_found() -> None:
    record = _make_record()
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([record]))

    found = await get_rainfall_record(db, 1, tenant_id=1)

    assert found is record


@pytest.mark.asyncio
async def test_get_rainfall_record_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_rainfall_record(db, 99, tenant_id=1)

    assert found is None


@pytest.mark.asyncio
async def test_get_rainfall_record_wrong_user() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_rainfall_record(db, 1, tenant_id=2)

    assert found is None


# ---------------------------------------------------------------------------
# list_rainfall_records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rainfall_records_empty() -> None:
    db = MagicMock()
    # 1st call: Plot.municipio_cod query; 2nd: RainfallRecord query
    db.execute = AsyncMock(side_effect=[result([]), result([])])

    records = await list_rainfall_records(db, tenant_id=1)

    assert records == []


@pytest.mark.asyncio
async def test_list_rainfall_records_returns_results() -> None:
    records_data = [_make_record(id=1), _make_record(id=2)]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result(records_data)])

    records = await list_rainfall_records(db, tenant_id=1)

    assert len(records) == 2


@pytest.mark.asyncio
async def test_list_rainfall_records_filters_by_year() -> None:
    # campaign_year(2025-11-10) = 2025; campaign_year(2026-04-01) = 2025
    r1 = _make_record(id=1, date=datetime.date(2025, 11, 10))
    r2 = _make_record(id=2, date=datetime.date(2024, 6, 1))
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result([r1, r2])])

    records = await list_rainfall_records(db, tenant_id=1, year=2025)

    assert len(records) == 1
    assert records[0].id == 1


@pytest.mark.asyncio
async def test_list_rainfall_records_filtered_by_plot() -> None:
    records_data = [_make_record(plot_id=3)]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result(records_data)])

    records = await list_rainfall_records(db, tenant_id=1, plot_id=3)

    assert len(records) == 1


@pytest.mark.asyncio
async def test_list_rainfall_records_filtered_by_municipio() -> None:
    records_data = [_make_record(plot_id=None, municipio_cod="44216")]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result(records_data)])

    records = await list_rainfall_records(db, tenant_id=1, municipio_cod="44216")

    assert len(records) == 1


# ---------------------------------------------------------------------------
# create_rainfall_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rainfall_record_with_plot() -> None:
    plot = SimpleNamespace(id=1, tenant_id=1, name="Parcela A")
    record = _make_record()
    db = MagicMock()
    # First execute: plot lookup; second is avoided because flush/refresh use mocks
    db.execute = AsyncMock(return_value=result([plot]))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    data = RainfallCreate(
        plot_id=1,
        date=datetime.date(2025, 11, 10),
        precipitation_mm=12.5,
        source="manual",
    )
    await create_rainfall_record(db, tenant_id=1, data=data)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.tenant_id == 1
    assert added.plot_id == 1
    assert added.precipitation_mm == 12.5
    assert added.source == "manual"


@pytest.mark.asyncio
async def test_create_rainfall_record_municipio_level() -> None:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    data = RainfallCreate(
        municipio_cod="44216",
        date=datetime.date(2025, 11, 10),
        precipitation_mm=8.0,
        source="manual",
    )
    await create_rainfall_record(db, tenant_id=1, data=data)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.plot_id is None
    assert added.municipio_cod == "44216"
    assert added.source == "manual"


@pytest.mark.asyncio
async def test_create_rainfall_record_non_manual_source_raises_400() -> None:
    from fastapi import HTTPException

    db = MagicMock()

    data = RainfallCreate(
        municipio_cod="44216",
        date=datetime.date(2025, 11, 10),
        precipitation_mm=8.0,
        source="aemet",
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_rainfall_record(db, tenant_id=1, data=data)

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_rainfall_record_plot_not_found() -> None:
    from fastapi import HTTPException

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    data = RainfallCreate(
        plot_id=99,
        date=datetime.date(2025, 11, 10),
        precipitation_mm=5.0,
    )
    with pytest.raises(HTTPException) as exc_info:
        await create_rainfall_record(db, tenant_id=1, data=data)

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# update_rainfall_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_rainfall_record_changes_fields() -> None:
    record = _make_record(precipitation_mm=10.0)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([record]))
    db.flush = AsyncMock()
    db.refresh = AsyncMock()

    data = RainfallUpdate(precipitation_mm=25.0, notes="Actualizado")
    await update_rainfall_record(db, record_id=1, tenant_id=1, data=data)

    assert record.precipitation_mm == 25.0
    assert record.notes == "Actualizado"


@pytest.mark.asyncio
async def test_update_rainfall_record_not_found() -> None:
    from fastapi import HTTPException

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    data = RainfallUpdate(precipitation_mm=5.0)
    with pytest.raises(HTTPException) as exc_info:
        await update_rainfall_record(db, record_id=99, tenant_id=1, data=data)

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# delete_rainfall_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_rainfall_record() -> None:
    record = _make_record()
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([record]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    await delete_rainfall_record(db, record_id=1, tenant_id=1)

    db.delete.assert_called_once_with(record)


@pytest.mark.asyncio
async def test_delete_rainfall_record_not_found() -> None:
    from fastapi import HTTPException

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    with pytest.raises(HTTPException) as exc_info:
        await delete_rainfall_record(db, record_id=99, tenant_id=1)

    assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# get_rainfall_for_plot_on_date
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rainfall_for_plot_on_date_exact_match() -> None:
    record = _make_record(plot_id=1)
    plot = SimpleNamespace(id=1, municipio_cod="44216")
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([record]))

    found = await get_rainfall_for_plot_on_date(
        db, plot, datetime.date(2025, 11, 10), tenant_id=1
    )

    assert found is record


@pytest.mark.asyncio
async def test_get_rainfall_for_plot_on_date_fallback_municipio() -> None:
    # First call (plot-specific) returns nothing; second (municipio) returns record
    municipio_record = _make_record(plot_id=None, municipio_cod="44216")
    plot = SimpleNamespace(id=1, municipio_cod="44216")
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result([municipio_record])])

    found = await get_rainfall_for_plot_on_date(
        db, plot, datetime.date(2025, 11, 10), tenant_id=1
    )

    assert found is municipio_record
    assert db.execute.call_count == 2


@pytest.mark.asyncio
async def test_get_rainfall_for_plot_on_date_no_data() -> None:
    plot = SimpleNamespace(id=1, municipio_cod="44216")
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result([])])

    found = await get_rainfall_for_plot_on_date(
        db, plot, datetime.date(2025, 11, 10), tenant_id=1
    )

    assert found is None


@pytest.mark.asyncio
async def test_get_rainfall_for_plot_on_date_no_municipio_cod() -> None:
    plot = SimpleNamespace(id=1, municipio_cod=None)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_rainfall_for_plot_on_date(
        db, plot, datetime.date(2025, 11, 10), tenant_id=1
    )

    assert found is None
    # Only one execute call (no fallback when municipio_cod is None)
    assert db.execute.call_count == 1


# ---------------------------------------------------------------------------
# get_rainfall_list_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rainfall_list_context_structure() -> None:
    from unittest.mock import patch

    records_data = [_make_record()]
    plots = [SimpleNamespace(id=1, name="Parcela A")]
    db = MagicMock()

    async def fake_list(*args, **kwargs):
        return records_data

    async def fake_get_plots(*args, **kwargs):
        return plots

    async def fake_get_years(*args, **kwargs):
        return [2025]

    async def fake_get_municipios(*args, **kwargs):
        return []

    with (
        patch("app.services.rainfall_service.list_rainfall_records", fake_list),
        patch("app.services.rainfall_service._get_user_plots", fake_get_plots),
        patch("app.services.rainfall_service._get_all_years", fake_get_years),
        patch(
            "app.services.rainfall_service._get_tenant_municipios", fake_get_municipios
        ),
    ):
        context = await get_rainfall_list_context(db, tenant_id=1)

    assert "records" in context
    assert "plots" in context
    assert "years" in context
    assert "municipios" in context
    assert "total_mm" in context
    assert "count" in context
    assert context["count"] == 1
    assert context["total_mm"] == 12.5


# ---------------------------------------------------------------------------
# _build_calendar_months  (función auxiliar pura, no necesita DB)
# ---------------------------------------------------------------------------


def test_build_calendar_months_structure() -> None:
    """La campaña 2025 debe generar exactamente 12 meses (Mayo 2025 - Abril 2026)."""
    months = _build_calendar_months(2025, {})

    assert len(months) == 12
    assert months[0]["month"] == 5 and months[0]["year"] == 2025
    assert months[-1]["month"] == 4 and months[-1]["year"] == 2026


def test_build_calendar_months_rain_totals() -> None:
    """Los totales mensuales deben reflejar la precipitación registrada."""
    rain = {
        datetime.date(2025, 11, 5): 10.0,
        datetime.date(2025, 11, 20): 5.0,
        datetime.date(2025, 12, 1): 8.0,
    }
    months = _build_calendar_months(2025, rain)

    nov = next(m for m in months if m["month"] == 11)
    dec = next(m for m in months if m["month"] == 12)
    may = next(m for m in months if m["month"] == 5 and m["year"] == 2025)

    assert nov["total_mm"] == 15.0
    assert nov["rain_days"] == 2
    assert dec["total_mm"] == 8.0
    assert dec["rain_days"] == 1
    assert may["total_mm"] == 0.0
    assert may["rain_days"] == 0


def test_build_calendar_months_css_classes() -> None:
    """Los días deben clasificarse correctamente por banda de precipitación."""
    rain = {
        datetime.date(2025, 5, 1): 0.0,
        datetime.date(2025, 5, 2): 2.0,  # low
        datetime.date(2025, 5, 3): 10.0,  # moderate
        datetime.date(2025, 5, 4): 20.0,  # heavy
        datetime.date(2025, 5, 5): 35.0,  # very-heavy
    }
    months = _build_calendar_months(2025, rain)
    may = next(m for m in months if m["month"] == 5 and m["year"] == 2025)

    # Aplanar todos los días del mes
    all_days = {
        cell["day"]: cell for week in may["weeks"] for cell in week if cell is not None
    }

    assert all_days[1]["css"] == "rain-none"
    assert all_days[2]["css"] == "rain-low"
    assert all_days[3]["css"] == "rain-moderate"
    assert all_days[4]["css"] == "rain-heavy"
    assert all_days[5]["css"] == "rain-very-heavy"


def test_build_calendar_months_week_padding() -> None:
    """Las semanas deben tener exactamente 7 celdas (con None como relleno)."""
    months = _build_calendar_months(2025, {})
    for month in months:
        for week in month["weeks"]:
            assert len(week) == 7


def test_build_calendar_months_m3_with_area() -> None:
    """Con area_ha, cada día y mes deben incluir el volumen en m³."""
    rain = {
        datetime.date(2025, 5, 10): 20.0,  # 20 mm × 3 ha × 10 = 600 m³
    }
    months = _build_calendar_months(2025, rain, area_ha=3.0)
    may = next(m for m in months if m["month"] == 5 and m["year"] == 2025)

    assert may["total_m3"] == 600.0
    all_days = {
        cell["day"]: cell for week in may["weeks"] for cell in week if cell is not None
    }
    assert all_days[10]["m3"] == 600.0
    # Un día sin lluvia tiene m3 = 0.0 (no None)
    assert all_days[1]["m3"] == 0.0


def test_build_calendar_months_m3_without_area() -> None:
    """Sin area_ha, m3 debe ser None en días y meses."""
    rain = {datetime.date(2025, 5, 10): 20.0}
    months = _build_calendar_months(2025, rain)
    may = next(m for m in months if m["month"] == 5 and m["year"] == 2025)

    assert may["total_m3"] is None
    all_days = {
        cell["day"]: cell for week in may["weeks"] for cell in week if cell is not None
    }
    assert all_days[10]["m3"] is None


# ---------------------------------------------------------------------------
# get_rainfall_calendar_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rainfall_calendar_context_structure() -> None:
    """El contexto debe incluir los campos requeridos por el template."""
    from unittest.mock import patch

    records_data = [
        _make_record(date=datetime.date(2025, 11, 5), precipitation_mm=8.0),
        _make_record(id=2, date=datetime.date(2025, 11, 20), precipitation_mm=3.0),
    ]
    plots = [SimpleNamespace(id=1, name="Parcela A")]
    db = MagicMock()

    async def fake_list(*args, **kwargs):
        return records_data

    async def fake_get_plots(*args, **kwargs):
        return plots

    async def fake_get_years(*args, **kwargs):
        return [2025]

    async def fake_get_municipios(*args, **kwargs):
        return []

    with (
        patch("app.services.rainfall_service.list_rainfall_records", fake_list),
        patch("app.services.rainfall_service._get_user_plots", fake_get_plots),
        patch("app.services.rainfall_service._get_all_years", fake_get_years),
        patch(
            "app.services.rainfall_service._get_tenant_municipios", fake_get_municipios
        ),
    ):
        context = await get_rainfall_calendar_context(db, tenant_id=1, year=2025)

    assert "months" in context
    assert len(context["months"]) == 12
    assert context["total_mm"] == 11.0
    assert context["total_m3"] is None  # sin parcela filtrada no hay área
    assert context["area_ha"] is None
    assert context["rain_days"] == 2
    assert context["selected_year"] == 2025
    assert "plots" in context
    assert "years" in context
    assert "day_labels" in context
    assert len(context["day_labels"]) == 7


@pytest.mark.asyncio
async def test_get_rainfall_calendar_context_with_plot_area() -> None:
    """Con plot_id y area_ha, el contexto debe incluir total_m3."""
    from unittest.mock import patch

    records_data = [
        _make_record(plot_id=1, date=datetime.date(2025, 11, 5), precipitation_mm=10.0),
    ]
    plot_obj = SimpleNamespace(id=1, tenant_id=1, area_ha=2.0, name="Bancal A")
    plots = [plot_obj]
    db = MagicMock()

    async def fake_list(*args, **kwargs):
        return records_data

    async def fake_get_plots(*args, **kwargs):
        return plots

    async def fake_get_years(*args, **kwargs):
        return [2025]

    async def fake_get_municipios(*args, **kwargs):
        return []

    async def fake_plot_lookup(*a, **kw):
        return result([plot_obj])

    with (
        patch("app.services.rainfall_service.list_rainfall_records", fake_list),
        patch("app.services.rainfall_service._get_user_plots", fake_get_plots),
        patch("app.services.rainfall_service._get_all_years", fake_get_years),
        patch(
            "app.services.rainfall_service._get_tenant_municipios", fake_get_municipios
        ),
    ):
        db.execute = AsyncMock(return_value=result([plot_obj]))
        context = await get_rainfall_calendar_context(
            db, tenant_id=1, year=2025, plot_id=1
        )

    # 10 mm × 2 ha × 10 = 200 m³
    assert context["area_ha"] == 2.0
    assert context["total_m3"] == 200.0


@pytest.mark.asyncio
async def test_get_rainfall_calendar_context_no_records() -> None:
    """Sin registros el total debe ser 0 y rain_days 0."""
    from unittest.mock import patch

    db = MagicMock()

    async def fake_list(*args, **kwargs):
        return []

    async def fake_empty(*args, **kwargs):
        return []

    with (
        patch("app.services.rainfall_service.list_rainfall_records", fake_list),
        patch("app.services.rainfall_service._get_user_plots", fake_empty),
        patch("app.services.rainfall_service._get_all_years", fake_empty),
        patch("app.services.rainfall_service._get_tenant_municipios", fake_empty),
    ):
        context = await get_rainfall_calendar_context(db, tenant_id=1, year=2024)

    assert context["total_mm"] == 0.0
    assert context["rain_days"] == 0
    assert len(context["months"]) == 12


@pytest.mark.asyncio
async def test_get_rainfall_calendar_context_source_filter() -> None:
    """El parámetro source se pasa a list_rainfall_records y se incluye en el contexto."""
    from unittest.mock import patch

    db = MagicMock()
    captured: dict = {}

    async def fake_list(*args, **kwargs):
        captured["source"] = kwargs.get("source")
        return []

    async def fake_empty(*args, **kwargs):
        return []

    with (
        patch("app.services.rainfall_service.list_rainfall_records", fake_list),
        patch("app.services.rainfall_service._get_user_plots", fake_empty),
        patch("app.services.rainfall_service._get_all_years", fake_empty),
        patch("app.services.rainfall_service._get_tenant_municipios", fake_empty),
    ):
        context = await get_rainfall_calendar_context(
            db, tenant_id=1, year=2025, source="aemet"
        )

    assert captured["source"] == "aemet"
    assert context["selected_source"] == "aemet"

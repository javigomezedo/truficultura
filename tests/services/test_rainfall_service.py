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
    get_rainfall_for_plot_on_date,
    get_rainfall_list_context,
    get_rainfall_record,
    list_rainfall_records,
    update_rainfall_record,
)
from tests.conftest import result


def _make_record(**kwargs) -> RainfallRecord:
    defaults = dict(
        id=1,
        user_id=1,
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

    found = await get_rainfall_record(db, 1, user_id=1)

    assert found is record


@pytest.mark.asyncio
async def test_get_rainfall_record_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_rainfall_record(db, 99, user_id=1)

    assert found is None


@pytest.mark.asyncio
async def test_get_rainfall_record_wrong_user() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_rainfall_record(db, 1, user_id=2)

    assert found is None


# ---------------------------------------------------------------------------
# list_rainfall_records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_rainfall_records_empty() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    records = await list_rainfall_records(db, user_id=1)

    assert records == []


@pytest.mark.asyncio
async def test_list_rainfall_records_returns_results() -> None:
    records_data = [_make_record(id=1), _make_record(id=2)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(records_data))

    records = await list_rainfall_records(db, user_id=1)

    assert len(records) == 2


@pytest.mark.asyncio
async def test_list_rainfall_records_filters_by_year() -> None:
    # campaign_year(2025-11-10) = 2025; campaign_year(2026-04-01) = 2025
    r1 = _make_record(id=1, date=datetime.date(2025, 11, 10))
    r2 = _make_record(id=2, date=datetime.date(2024, 6, 1))
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([r1, r2]))

    records = await list_rainfall_records(db, user_id=1, year=2025)

    assert len(records) == 1
    assert records[0].id == 1


@pytest.mark.asyncio
async def test_list_rainfall_records_filtered_by_plot() -> None:
    records_data = [_make_record(plot_id=3)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(records_data))

    records = await list_rainfall_records(db, user_id=1, plot_id=3)

    assert len(records) == 1


@pytest.mark.asyncio
async def test_list_rainfall_records_filtered_by_municipio() -> None:
    records_data = [_make_record(plot_id=None, municipio_cod="44216")]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(records_data))

    records = await list_rainfall_records(db, user_id=1, municipio_cod="44216")

    assert len(records) == 1


# ---------------------------------------------------------------------------
# create_rainfall_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_rainfall_record_with_plot() -> None:
    plot = SimpleNamespace(id=1, user_id=1, name="Parcela A")
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
    await create_rainfall_record(db, user_id=1, data=data)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.user_id == 1
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
        source="aemet",
    )
    await create_rainfall_record(db, user_id=1, data=data)

    db.add.assert_called_once()
    added = db.add.call_args[0][0]
    assert added.plot_id is None
    assert added.municipio_cod == "44216"
    assert added.source == "aemet"


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
        await create_rainfall_record(db, user_id=1, data=data)

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
    await update_rainfall_record(db, record_id=1, user_id=1, data=data)

    assert record.precipitation_mm == 25.0
    assert record.notes == "Actualizado"


@pytest.mark.asyncio
async def test_update_rainfall_record_not_found() -> None:
    from fastapi import HTTPException

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    data = RainfallUpdate(precipitation_mm=5.0)
    with pytest.raises(HTTPException) as exc_info:
        await update_rainfall_record(db, record_id=99, user_id=1, data=data)

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

    await delete_rainfall_record(db, record_id=1, user_id=1)

    db.delete.assert_called_once_with(record)


@pytest.mark.asyncio
async def test_delete_rainfall_record_not_found() -> None:
    from fastapi import HTTPException

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    with pytest.raises(HTTPException) as exc_info:
        await delete_rainfall_record(db, record_id=99, user_id=1)

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
        db, plot, datetime.date(2025, 11, 10), user_id=1
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
        db, plot, datetime.date(2025, 11, 10), user_id=1
    )

    assert found is municipio_record
    assert db.execute.call_count == 2


@pytest.mark.asyncio
async def test_get_rainfall_for_plot_on_date_no_data() -> None:
    plot = SimpleNamespace(id=1, municipio_cod="44216")
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result([])])

    found = await get_rainfall_for_plot_on_date(
        db, plot, datetime.date(2025, 11, 10), user_id=1
    )

    assert found is None


@pytest.mark.asyncio
async def test_get_rainfall_for_plot_on_date_no_municipio_cod() -> None:
    plot = SimpleNamespace(id=1, municipio_cod=None)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_rainfall_for_plot_on_date(
        db, plot, datetime.date(2025, 11, 10), user_id=1
    )

    assert found is None
    # Only one execute call (no fallback when municipio_cod is None)
    assert db.execute.call_count == 1


# ---------------------------------------------------------------------------
# get_rainfall_list_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_rainfall_list_context_structure() -> None:
    records_data = [_make_record()]
    plots = [SimpleNamespace(id=1, name="Parcela A")]
    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result(records_data), result(plots), result([]), result([])]
    )

    context = await get_rainfall_list_context(db, user_id=1)

    assert "records" in context
    assert "plots" in context
    assert "years" in context
    assert "municipios" in context
    assert "total_mm" in context
    assert "count" in context
    assert context["count"] == 1
    assert context["total_mm"] == 12.5

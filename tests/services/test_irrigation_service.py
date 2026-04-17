from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.expense import Expense
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.schemas.irrigation import IrrigationCreate, IrrigationUpdate
from app.services.irrigation_service import (
    create_irrigation_record,
    delete_irrigation_record,
    get_irrigation_list_context,
    get_irrigation_record,
    get_riego_expenses_for_plot,
    list_irrigation_records,
    update_irrigation_record,
)
from tests.conftest import result


def _make_plot(id=1, has_irrigation=True):
    return Plot(
        id=id,
        user_id=1,
        name=f"Parcela {id}",
        planting_date=datetime.date(2020, 1, 1),
        has_irrigation=has_irrigation,
        percentage=100.0,
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=100,
    )


def _make_record(id=1, plot_id=1, water_m3=10.0, expense_id=None):
    r = IrrigationRecord(
        id=id,
        user_id=1,
        plot_id=plot_id,
        date=datetime.date(2025, 6, 15),
        water_m3=water_m3,
        expense_id=expense_id,
        notes=None,
    )
    r.plot = _make_plot(id=plot_id)
    r.expense = None
    return r


# ---------------------------------------------------------------------------
# get_irrigation_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_irrigation_record_found() -> None:
    record = _make_record()
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([record]))

    found = await get_irrigation_record(db, record_id=1, user_id=1)
    assert found is record


@pytest.mark.asyncio
async def test_get_irrigation_record_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    found = await get_irrigation_record(db, record_id=99, user_id=1)
    assert found is None


# ---------------------------------------------------------------------------
# list_irrigation_records — filters by user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_irrigation_records_filters_by_user_id() -> None:
    records = [_make_record(id=1), _make_record(id=2)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(records))

    found = await list_irrigation_records(db, user_id=1)
    assert len(found) == 2
    # Verifica que la query ejecutada filtra correctamente
    call_args = db.execute.call_args[0][0]
    where_clauses = str(call_args)
    assert "user_id" in where_clauses


@pytest.mark.asyncio
async def test_list_irrigation_records_filter_by_year() -> None:
    # record en campaña 2025 (junio 2025 → campaign_year = 2025)
    r_2025 = _make_record(id=1)
    r_2025.date = datetime.date(2025, 6, 15)  # campaign_year = 2025

    # record en campaña 2024 (junio 2024 → campaign_year = 2024)
    r_2024 = _make_record(id=2)
    r_2024.date = datetime.date(2024, 6, 10)  # campaign_year = 2024

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([r_2025, r_2024]))

    found = await list_irrigation_records(db, user_id=1, year=2025)
    assert all(r.date.year >= 2025 for r in found)
    assert len(found) == 1


# ---------------------------------------------------------------------------
# get_irrigation_list_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_irrigation_list_context_totals() -> None:
    records = [_make_record(id=1, water_m3=5.0), _make_record(id=2, water_m3=3.0)]
    plot = _make_plot()

    db = MagicMock()
    # execute se llama 3 veces: records, plots irrigables, años
    db.execute = AsyncMock(side_effect=[result(records), result([plot]), result([])])

    ctx = await get_irrigation_list_context(db, user_id=1)
    assert ctx["count"] == 2
    assert ctx["total_water_m3"] == 8.0
    assert ctx["total_water_liters"] == 8000.0


# ---------------------------------------------------------------------------
# get_riego_expenses_for_plot — filters by category "Riego"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_riego_expenses_filters_by_category() -> None:
    expense = Expense(
        id=1,
        user_id=1,
        plot_id=1,
        date=datetime.date(2025, 5, 1),
        description="Agua mayo",
        amount=120.0,
        category="Riego",
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([expense]))

    expenses = await get_riego_expenses_for_plot(db, user_id=1, plot_id=1)

    assert len(expenses) == 1
    assert expenses[0].category == "Riego"
    call_str = str(db.execute.call_args[0][0])
    assert "category" in call_str.lower() or "Riego" in str(db.execute.call_args)


# ---------------------------------------------------------------------------
# create_irrigation_record — validaciones
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_validates_plot_has_irrigation() -> None:
    """Debe lanzar HTTPException si la parcela tiene has_irrigation=False."""
    from fastapi import HTTPException

    plot_no_riego = _make_plot(has_irrigation=False)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot_no_riego]))

    data = IrrigationCreate(plot_id=1, date=datetime.date(2025, 6, 1), water_m3=5.0)

    with pytest.raises(HTTPException) as exc_info:
        await create_irrigation_record(db, user_id=1, data=data)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_validates_plot_not_found() -> None:
    """Debe lanzar HTTPException 404 si la parcela no existe para ese user."""
    from fastapi import HTTPException

    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    data = IrrigationCreate(plot_id=999, date=datetime.date(2025, 6, 1), water_m3=5.0)

    with pytest.raises(HTTPException) as exc_info:
        await create_irrigation_record(db, user_id=1, data=data)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_validates_expense_category_riego() -> None:
    """Debe lanzar HTTPException si el gasto proporcionado no cumple los requisitos."""
    from fastapi import HTTPException

    plot = _make_plot(has_irrigation=True)
    db = MagicMock()
    # Primera llamada: plot encontrado; segunda: gasto no encontrado (categoría incorrecta)
    db.execute = AsyncMock(side_effect=[result([plot]), result([])])

    data = IrrigationCreate(
        plot_id=1,
        date=datetime.date(2025, 6, 1),
        water_m3=5.0,
        expense_id=42,
    )

    with pytest.raises(HTTPException) as exc_info:
        await create_irrigation_record(db, user_id=1, data=data)
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_success() -> None:
    plot = _make_plot(has_irrigation=True)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))
    db.add = MagicMock()
    db.flush = AsyncMock()

    data = IrrigationCreate(plot_id=1, date=datetime.date(2025, 6, 1), water_m3=12.5)

    with patch(
        "app.services.plot_events_service.sync_plot_event_from_irrigation",
        new=AsyncMock(),
    ) as sync_mock:
        record = await create_irrigation_record(db, user_id=1, data=data)

    db.add.assert_called_once()
    db.flush.assert_awaited()
    sync_mock.assert_awaited_once()
    assert record.water_m3 == 12.5
    assert record.user_id == 1


# ---------------------------------------------------------------------------
# update_irrigation_record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_irrigation_record() -> None:
    record = _make_record(water_m3=5.0)
    db = MagicMock()
    db.flush = AsyncMock()

    data = IrrigationUpdate(water_m3=20.0, notes="Actualizado")
    with patch(
        "app.services.plot_events_service.sync_plot_event_from_irrigation",
        new=AsyncMock(),
    ) as sync_mock:
        updated = await update_irrigation_record(db, record, data)

    assert updated.water_m3 == 20.0
    assert updated.notes == "Actualizado"
    db.flush.assert_awaited()
    sync_mock.assert_awaited_once()


# ---------------------------------------------------------------------------
# delete_irrigation_record — respeta user_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_enforces_user_id() -> None:
    """Si el registro no pertenece al user, no se llama a db.delete."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))  # no encontrado
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    await delete_irrigation_record(db, record_id=1, user_id=99)
    db.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_success() -> None:
    record = _make_record()
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([record]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    with patch(
        "app.services.plot_events_service.delete_plot_event_for_irrigation",
        new=AsyncMock(),
    ) as delete_event_mock:
        await delete_irrigation_record(db, record_id=1, user_id=1)

    db.delete.assert_awaited_once_with(record)
    delete_event_mock.assert_awaited_once_with(db, 1, 1)

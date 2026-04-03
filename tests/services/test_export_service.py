from __future__ import annotations

import csv
import datetime
import io
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.services.export_service import (
    export_expenses_csv,
    export_incomes_csv,
    export_irrigation_csv,
    export_plots_csv,
)
from tests.conftest import result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_plot(id=1, name="Bancal Sur", has_irrigation=False):
    return Plot(
        id=id,
        user_id=1,
        name=name,
        planting_date=datetime.date(2020, 3, 15),
        polygon="21",
        plot_num="120",
        cadastral_ref="44223A021001200000FP",
        hydrant="H-3",
        sector="S2",
        num_plants=120,
        area_ha=1.25,
        production_start=datetime.date(2023, 11, 1),
        percentage=100.0,
        has_irrigation=has_irrigation,
    )


def _make_expense(id=1, plot_id=1, amount=1250.0, category="Riego"):
    return Expense(
        id=id,
        user_id=1,
        date=datetime.date(2025, 11, 15),
        description="Riego por goteo",
        person="Javi",
        plot_id=plot_id,
        amount=amount,
        category=category,
    )


def _make_income(id=1, plot_id=1, amount_kg=2.5, euros_per_kg=120.0, category="Extra"):
    return Income(
        id=id,
        user_id=1,
        date=datetime.date(2025, 12, 5),
        plot_id=plot_id,
        amount_kg=amount_kg,
        category=category,
        euros_per_kg=euros_per_kg,
    )


def _make_irrigation(id=1, plot_id=1, water_m3=10.5, notes=None):
    return IrrigationRecord(
        id=id,
        user_id=1,
        plot_id=plot_id,
        date=datetime.date(2025, 6, 15),
        water_m3=water_m3,
        notes=notes,
        expense_id=None,
    )


def _parse_csv(data: bytes) -> list[list[str]]:
    return list(csv.reader(io.StringIO(data.decode("utf-8")), delimiter=";"))


def _db_with_two_calls(first_result, second_result):
    """Return a mock db whose execute is called twice: once for plots, once for entities."""
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[first_result, second_result])
    return db


# ---------------------------------------------------------------------------
# export_plots_csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_plots_csv_returns_correct_rows():
    plot = _make_plot(id=1, has_irrigation=True)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))

    data = await export_plots_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "Bancal Sur"
    assert row[1] == "15/03/2020"
    assert row[2] == "21"
    assert row[3] == "120"
    assert row[4] == "44223A021001200000FP"
    assert row[5] == "H-3"
    assert row[6] == "S2"
    assert row[7] == "120"
    assert row[8] == "1,2500"  # area_ha 4 decimals
    assert row[9] == "01/11/2023"  # production_start
    assert row[10] == "1"  # has_irrigation=True


@pytest.mark.asyncio
async def test_export_plots_csv_has_irrigation_false():
    plot = _make_plot(id=1, has_irrigation=False)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))

    data = await export_plots_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert rows[0][10] == "0"


@pytest.mark.asyncio
async def test_export_plots_csv_no_optional_fields():
    plot = Plot(
        id=2,
        user_id=1,
        name="Parcela Mínima",
        planting_date=datetime.date(2021, 5, 1),
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=0,
        area_ha=None,
        production_start=None,
        percentage=0.0,
        has_irrigation=False,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([plot]))

    data = await export_plots_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert rows[0][8] == ""  # area_ha empty
    assert rows[0][9] == ""  # production_start empty
    assert rows[0][10] == "0"


@pytest.mark.asyncio
async def test_export_plots_csv_empty():
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    data = await export_plots_csv(db, user_id=1)
    assert data == b""


# ---------------------------------------------------------------------------
# export_expenses_csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_expenses_csv_with_plot():
    plot = _make_plot(id=1, name="Bancal Sur")
    expense = _make_expense(id=1, plot_id=1)
    db = _db_with_two_calls(result([plot]), result([expense]))

    data = await export_expenses_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "15/11/2025"
    assert row[1] == "Riego por goteo"
    assert row[2] == "Javi"
    assert row[3] == "Bancal Sur"
    assert row[4] == "1250,00"
    assert row[5] == "Riego"


@pytest.mark.asyncio
async def test_export_expenses_csv_general_expense():
    plot = _make_plot(id=1)
    expense = _make_expense(id=1, plot_id=None, category=None)
    expense.plot_id = None
    expense.category = None
    db = _db_with_two_calls(result([plot]), result([expense]))

    data = await export_expenses_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert rows[0][3] == ""  # bancal empty
    assert rows[0][5] == ""  # categoria empty


@pytest.mark.asyncio
async def test_export_expenses_csv_empty():
    db = _db_with_two_calls(result([]), result([]))

    data = await export_expenses_csv(db, user_id=1)
    assert data == b""


# ---------------------------------------------------------------------------
# export_incomes_csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_incomes_csv_with_plot():
    plot = _make_plot(id=1, name="Bancal Norte")
    income = _make_income(id=1, plot_id=1)
    db = _db_with_two_calls(result([plot]), result([income]))

    data = await export_incomes_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "05/12/2025"
    assert row[1] == "Bancal Norte"
    assert row[2] == "2,500"  # 3 decimals
    assert row[3] == "Extra"
    assert row[4] == "120,00"


@pytest.mark.asyncio
async def test_export_incomes_csv_no_plot():
    income = _make_income(id=1, plot_id=None)
    income.plot_id = None
    db = _db_with_two_calls(result([]), result([income]))

    data = await export_incomes_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert rows[0][1] == ""  # bancal empty


@pytest.mark.asyncio
async def test_export_incomes_csv_empty():
    db = _db_with_two_calls(result([]), result([]))

    data = await export_incomes_csv(db, user_id=1)
    assert data == b""


# ---------------------------------------------------------------------------
# export_irrigation_csv
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_irrigation_csv_with_data():
    plot = _make_plot(id=1, name="Via Minera", has_irrigation=True)
    record = _make_irrigation(id=1, plot_id=1, water_m3=12.345, notes="Primera pasada")
    db = _db_with_two_calls(result([plot]), result([record]))

    data = await export_irrigation_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert len(rows) == 1
    row = rows[0]
    assert row[0] == "15/06/2025"
    assert row[1] == "Via Minera"
    assert row[2] == "12,345"  # 3 decimals EU format
    assert row[3] == "Primera pasada"


@pytest.mark.asyncio
async def test_export_irrigation_csv_no_notes():
    plot = _make_plot(id=1, name="Via Minera", has_irrigation=True)
    record = _make_irrigation(id=1, plot_id=1, water_m3=5.0, notes=None)
    db = _db_with_two_calls(result([plot]), result([record]))

    data = await export_irrigation_csv(db, user_id=1)
    rows = _parse_csv(data)

    assert rows[0][3] == ""  # notes empty


@pytest.mark.asyncio
async def test_export_irrigation_csv_empty():
    db = _db_with_two_calls(result([]), result([]))

    data = await export_irrigation_csv(db, user_id=1)
    assert data == b""

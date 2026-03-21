from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.gasto import Gasto
from app.models.ingreso import Ingreso
from app.services.gastos_service import (
    create_gasto,
    delete_gasto,
    get_gasto,
    get_gastos_list_context,
    update_gasto,
)
from app.services.ingresos_service import (
    create_ingreso,
    delete_ingreso,
    get_ingreso,
    get_ingresos_list_context,
    update_ingreso,
)
from tests.conftest import result


@pytest.mark.asyncio
async def test_gastos_list_context_filters_by_campaign() -> None:
    gastos = [
        Gasto(id=1, fecha=datetime.date(2025, 5, 1), concepto="A", cantidad=10.0),
        Gasto(id=2, fecha=datetime.date(2026, 2, 1), concepto="B", cantidad=5.0),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(gastos))

    context = await get_gastos_list_context(db, 2025)

    assert context["selected_year"] == 2025
    assert len(context["gastos"]) == 2
    assert context["total"] == 15.0
    assert 2025 in context["years"]


@pytest.mark.asyncio
async def test_ingresos_list_context_filters_by_campaign() -> None:
    ingresos = [
        Ingreso(
            id=1,
            fecha=datetime.date(2025, 6, 1),
            cantidad_kg=2.0,
            euros_kg=10.0,
            total=20.0,
        ),
        Ingreso(
            id=2,
            fecha=datetime.date(2026, 1, 15),
            cantidad_kg=1.0,
            euros_kg=15.0,
            total=15.0,
        ),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(ingresos))

    context = await get_ingresos_list_context(db, 2025)

    assert context["selected_year"] == 2025
    assert len(context["ingresos"]) == 2
    assert context["total_kg"] == 3.0
    assert context["total_euros"] == 35.0


@pytest.mark.asyncio
async def test_create_update_delete_gasto() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    gasto = await create_gasto(
        db,
        fecha=datetime.date(2025, 7, 1),
        concepto="Riego",
        persona="Javi",
        parcela_id=1,
        cantidad=50.0,
    )
    assert gasto.parcela_id == 1

    await update_gasto(
        db,
        gasto,
        fecha=datetime.date(2025, 8, 1),
        concepto="Riego 2",
        persona="Javi",
        parcela_id=None,
        cantidad=75.0,
    )
    assert gasto.parcela_id is None
    assert gasto.cantidad == 75.0

    await delete_gasto(db, gasto)
    db.delete.assert_awaited_once_with(gasto)


@pytest.mark.asyncio
async def test_create_update_delete_ingreso() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    ingreso = await create_ingreso(
        db,
        fecha=datetime.date(2025, 11, 1),
        parcela_id=2,
        cantidad_kg=3.0,
        categoria="A",
        euros_kg=100.0,
    )
    assert ingreso.total == 300.0

    await update_ingreso(
        db,
        ingreso,
        fecha=datetime.date(2025, 11, 2),
        parcela_id=None,
        cantidad_kg=4.0,
        categoria="B",
        euros_kg=80.0,
    )
    assert ingreso.total == 320.0
    assert ingreso.parcela_id is None

    await delete_ingreso(db, ingreso)
    db.delete.assert_awaited_once_with(ingreso)


@pytest.mark.asyncio
async def test_get_gasto_and_get_ingreso() -> None:
    gasto = Gasto(id=10, fecha=datetime.date(2025, 1, 1), concepto="X", cantidad=1.0)
    ingreso = Ingreso(
        id=20, fecha=datetime.date(2025, 1, 1), cantidad_kg=1.0, euros_kg=1.0, total=1.0
    )

    db_g = MagicMock()
    db_g.execute = AsyncMock(return_value=result([gasto]))
    assert await get_gasto(db_g, 10) is gasto

    db_i = MagicMock()
    db_i.execute = AsyncMock(return_value=result([ingreso]))
    assert await get_ingreso(db_i, 20) is ingreso

from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.gasto import Gasto
from app.models.ingreso import Ingreso
from app.models.parcela import Parcela
from app.services.dashboard_service import build_dashboard_context
from app.services.reportes_service import build_rentabilidad_context
from tests.conftest import result


@pytest.mark.asyncio
async def test_build_dashboard_context_returns_expected_totals() -> None:
    parcelas = [
        Parcela(
            id=1,
            nombre="P1",
            fecha_plantacion=datetime.date(2020, 1, 1),
            porcentaje=60.0,
        ),
        Parcela(
            id=2,
            nombre="P2",
            fecha_plantacion=datetime.date(2020, 1, 1),
            porcentaje=40.0,
        ),
    ]
    gastos = [
        Gasto(
            id=1,
            fecha=datetime.date(2025, 5, 1),
            concepto="A",
            parcela_id=1,
            cantidad=100.0,
        ),
        Gasto(
            id=2,
            fecha=datetime.date(2025, 5, 2),
            concepto="B",
            parcela_id=None,
            cantidad=50.0,
        ),
    ]
    ingresos = [
        Ingreso(
            id=1,
            fecha=datetime.date(2025, 6, 1),
            parcela_id=1,
            cantidad_kg=2.0,
            euros_kg=20.0,
            total=40.0,
        ),
        Ingreso(
            id=2,
            fecha=datetime.date(2025, 6, 2),
            parcela_id=2,
            cantidad_kg=1.0,
            euros_kg=30.0,
            total=30.0,
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result(parcelas), result(gastos), result(ingresos)]
    )

    context = await build_dashboard_context(db)

    assert context["total_parcelas"] == 2
    assert context["grand_gastos"] == 150.0
    assert context["grand_ingresos"] == 70.0
    assert context["grand_rentabilidad"] == -80.0
    assert len(context["campaign_rows"]) == 1


@pytest.mark.asyncio
async def test_build_rentabilidad_context_returns_matrix() -> None:
    parcelas = [
        Parcela(
            id=1,
            nombre="P1",
            fecha_plantacion=datetime.date(2020, 1, 1),
            porcentaje=100.0,
        ),
    ]
    ingresos = [
        Ingreso(
            id=1,
            fecha=datetime.date(2025, 12, 1),
            parcela_id=1,
            cantidad_kg=1.0,
            euros_kg=10.0,
            total=10.0,
        ),
    ]
    gastos = [
        Gasto(
            id=1,
            fecha=datetime.date(2025, 12, 2),
            concepto="R",
            parcela_id=1,
            cantidad=3.0,
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result(parcelas), result(ingresos), result(gastos)]
    )

    context = await build_rentabilidad_context(db)

    assert context["all_years"] == [2025]
    assert context["grand_total_ingresos"] == 10.0
    assert context["grand_total_gastos"] == 3.0
    assert context["grand_total_rentabilidad"] == 7.0
    assert len(context["matrix"]) == 1

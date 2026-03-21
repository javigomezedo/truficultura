from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.gasto import Gasto
from app.models.ingreso import Ingreso
from app.models.parcela import Parcela
from app.services.graficas_service import build_graficas_context
from tests.conftest import result


@pytest.mark.asyncio
async def test_build_graficas_context_generates_serialized_series() -> None:
    parcelas = [
        Parcela(
            id=1,
            nombre="P1",
            fecha_plantacion=datetime.date(2020, 1, 1),
            superficie_ha=1.0,
            porcentaje=100.0,
        ),
    ]
    gastos = [
        Gasto(
            id=1,
            fecha=datetime.date(2025, 12, 1),
            concepto="Riego",
            parcela_id=1,
            cantidad=5.0,
        ),
    ]
    ingresos = [
        Ingreso(
            id=1,
            fecha=datetime.date(2025, 12, 2),
            parcela_id=1,
            cantidad_kg=2.0,
            categoria="A",
            euros_kg=20.0,
            total=40.0,
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result(parcelas), result(gastos), result(ingresos)]
    )

    context = await build_graficas_context(db, campaign=2025, bancal_id=None)

    assert context["selected_campaign"] == 2025
    assert context["selected_bancal"] is None
    assert context["week_labels"].startswith("[")
    assert context["ing_values"].startswith("[")
    assert context["gas_values"].startswith("[")
    assert len(context["kg_ha_table"]) == 1

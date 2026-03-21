from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.parcela import Parcela
from app.services.parcelas_service import (
    create_parcela,
    delete_parcela,
    get_parcela,
    list_parcelas,
    update_parcela,
)
from tests.conftest import result


@pytest.mark.asyncio
async def test_list_parcelas_returns_ordered_items() -> None:
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=result(
            [Parcela(id=1, nombre="A", fecha_plantacion=datetime.date(2020, 1, 1))]
        )
    )

    parcelas = await list_parcelas(db)

    assert len(parcelas) == 1
    assert parcelas[0].nombre == "A"


@pytest.mark.asyncio
async def test_get_parcela_found_and_not_found() -> None:
    parcela = Parcela(id=7, nombre="Norte", fecha_plantacion=datetime.date(2019, 4, 1))

    db_found = MagicMock()
    db_found.execute = AsyncMock(return_value=result([parcela]))
    assert await get_parcela(db_found, 7) is parcela

    db_missing = MagicMock()
    db_missing.execute = AsyncMock(return_value=result([]))
    assert await get_parcela(db_missing, 8) is None


@pytest.mark.asyncio
async def test_create_update_delete_parcela() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    created = await create_parcela(
        db,
        nombre="Bancal Sur",
        poligono="5",
        parcela_catastro="42",
        hidrante="H-01",
        sector="S1",
        n_carrascas=120,
        fecha_plantacion=datetime.date(2021, 2, 3),
        superficie_ha=1.5,
        inicio_produccion=datetime.date(2024, 1, 1),
        porcentaje=40.0,
    )

    db.add.assert_called_once()
    db.flush.assert_awaited()
    assert created.nombre == "Bancal Sur"
    assert created.parcela == "42"

    updated = await update_parcela(
        db,
        created,
        nombre="Bancal Sur 2",
        poligono="6",
        parcela_catastro="43",
        hidrante="H-02",
        sector="S2",
        n_carrascas=130,
        fecha_plantacion=datetime.date(2021, 3, 3),
        superficie_ha=1.8,
        inicio_produccion=datetime.date(2024, 2, 1),
        porcentaje=45.0,
    )

    assert updated.nombre == "Bancal Sur 2"
    assert updated.parcela == "43"
    assert updated.porcentaje == 45.0

    await delete_parcela(db, created)
    db.delete.assert_awaited_once_with(created)

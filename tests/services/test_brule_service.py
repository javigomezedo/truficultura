from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.brule import BruleRecord
from app.services.brule_service import (
    create_brule_record,
    delete_brule_record,
    get_brule_evolution,
    get_brule_production_correlation,
    get_brule_record,
    get_last_brule_by_plant,
    list_brule_records,
    update_brule_record,
)
from tests.conftest import result


def _record(
    record_id: int = 1,
    tenant_id: int = 1,
    plant_id: int = 10,
    plot_id: int = 2,
    diameter_cm: int = 45,
    record_date: datetime.date = datetime.date(2025, 11, 5),
) -> BruleRecord:
    r = BruleRecord(
        id=record_id,
        tenant_id=tenant_id,
        plant_id=plant_id,
        plot_id=plot_id,
        diameter_cm=diameter_cm,
        record_date=record_date,
    )
    return r


# ─────────────────────────────────────────────────────────────────────────────
# list_brule_records
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_brule_records_returns_all_for_tenant() -> None:
    records = [_record(record_id=1), _record(record_id=2)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(records))

    out = await list_brule_records(db, tenant_id=1)

    assert len(out) == 2
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_brule_records_empty_when_none() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    out = await list_brule_records(db, tenant_id=1)

    assert out == []


@pytest.mark.asyncio
async def test_list_brule_records_filters_by_plant_id() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    await list_brule_records(db, tenant_id=1, plant_id=99)

    db.execute.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# get_brule_record
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_brule_record_found() -> None:
    rec = _record()
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([rec]))

    out = await get_brule_record(db, record_id=1, tenant_id=1)

    assert out is rec


@pytest.mark.asyncio
async def test_get_brule_record_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    out = await get_brule_record(db, record_id=999, tenant_id=1)

    assert out is None


# ─────────────────────────────────────────────────────────────────────────────
# create_brule_record
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_create_brule_record_adds_and_flushes() -> None:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    rec = await create_brule_record(
        db,
        tenant_id=1,
        plant_id=10,
        plot_id=2,
        record_date=datetime.date(2025, 11, 5),
        diameter_cm=50,
        user_id=7,
    )

    db.add.assert_called_once()
    db.flush.assert_awaited_once()
    assert rec.tenant_id == 1
    assert rec.plant_id == 10
    assert rec.plot_id == 2
    assert rec.diameter_cm == 50
    assert rec.created_by_user_id == 7


# ─────────────────────────────────────────────────────────────────────────────
# update_brule_record
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_brule_record_changes_diameter() -> None:
    rec = _record(diameter_cm=40)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([rec]))
    db.flush = AsyncMock()

    updated = await update_brule_record(db, record_id=1, tenant_id=1, diameter_cm=65)

    assert updated is rec
    assert updated.diameter_cm == 65
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_brule_record_not_found_returns_none() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.flush = AsyncMock()

    out = await update_brule_record(db, record_id=999, tenant_id=1, diameter_cm=60)

    assert out is None
    db.flush.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# delete_brule_record
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_brule_record_deletes_and_flushes() -> None:
    rec = _record()
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([rec]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    await delete_brule_record(db, record_id=1, tenant_id=1)

    db.delete.assert_awaited_once_with(rec)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_brule_record_noop_when_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    await delete_brule_record(db, record_id=999, tenant_id=1)

    db.delete.assert_not_awaited()
    db.flush.assert_not_awaited()


# ─────────────────────────────────────────────────────────────────────────────
# get_brule_evolution
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_brule_evolution_returns_tuples_ordered() -> None:
    row1 = SimpleNamespace(record_date=datetime.date(2025, 6, 1), diameter_cm=40)
    row2 = SimpleNamespace(record_date=datetime.date(2025, 10, 1), diameter_cm=55)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([row1, row2]))

    out = await get_brule_evolution(db, tenant_id=1, plant_id=10)

    assert out == [(datetime.date(2025, 6, 1), 40), (datetime.date(2025, 10, 1), 55)]


@pytest.mark.asyncio
async def test_get_brule_evolution_empty() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    out = await get_brule_evolution(db, tenant_id=1, plant_id=99)

    assert out == []


# ─────────────────────────────────────────────────────────────────────────────
# get_last_brule_by_plant
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_last_brule_by_plant_returns_dict() -> None:
    row1 = SimpleNamespace(plant_id=10, diameter_cm=55)
    row2 = SimpleNamespace(plant_id=11, diameter_cm=30)
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([row1, row2]))

    out = await get_last_brule_by_plant(db, tenant_id=1, plot_id=2)

    assert out == {10: 55, 11: 30}


@pytest.mark.asyncio
async def test_get_last_brule_by_plant_empty_plot() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    out = await get_last_brule_by_plant(db, tenant_id=1, plot_id=99)

    assert out == {}


# ─────────────────────────────────────────────────────────────────────────────
# list_brule_records — campaign filter
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_brule_records_filters_by_campaign() -> None:
    rec = _record(record_date=datetime.date(2025, 11, 5))
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([rec]))

    out = await list_brule_records(db, tenant_id=1, campaign=2025)

    assert len(out) == 1
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_brule_records_filters_by_plot_and_campaign() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    out = await list_brule_records(db, tenant_id=1, plot_id=2, campaign=2025)

    assert out == []
    db.execute.assert_awaited_once()


# ─────────────────────────────────────────────────────────────────────────────
# get_brule_production_correlation
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_brule_production_correlation_empty_when_no_brule() -> None:
    db = MagicMock()
    # First execute call (brule subquery) returns empty rows
    db.execute = AsyncMock(return_value=result([]))

    out = await get_brule_production_correlation(db, tenant_id=1)

    assert out == []
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_brule_production_correlation_merges_brule_and_production() -> None:
    brule_row = SimpleNamespace(
        plant_id=10, diameter_cm=55, plant_label="A1", plot_name="Norte"
    )
    prod_row = SimpleNamespace(plant_id=10, total_grams=1500.0)

    execute_call_count = 0

    async def _execute(stmt):
        nonlocal execute_call_count
        execute_call_count += 1
        if execute_call_count == 1:
            return result([brule_row])
        return result([prod_row])

    db = MagicMock()
    db.execute = _execute

    out = await get_brule_production_correlation(db, tenant_id=1)

    assert len(out) == 1
    assert out[0]["plant_label"] == "A1"
    assert out[0]["last_diameter_cm"] == 55
    assert out[0]["total_weight_kg"] == 1.5


@pytest.mark.asyncio
async def test_get_brule_production_correlation_skips_plants_without_production() -> (
    None
):
    brule_row = SimpleNamespace(
        plant_id=10, diameter_cm=55, plant_label="A1", plot_name="Norte"
    )

    execute_call_count = 0

    async def _execute(stmt):
        nonlocal execute_call_count
        execute_call_count += 1
        if execute_call_count == 1:
            return result([brule_row])
        return result([])  # no production

    db = MagicMock()
    db.execute = _execute

    out = await get_brule_production_correlation(db, tenant_id=1)

    assert out == []


@pytest.mark.asyncio
async def test_get_brule_production_correlation_with_plot_and_campaign_filters() -> (
    None
):
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    out = await get_brule_production_correlation(
        db, tenant_id=1, plot_id=2, campaign=2025
    )

    assert out == []

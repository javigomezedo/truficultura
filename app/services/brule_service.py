from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.brule import BruleRecord


async def list_brule_records(
    db: AsyncSession,
    tenant_id: int,
    *,
    plot_id: Optional[int] = None,
    plant_id: Optional[int] = None,
    campaign: Optional[int] = None,
) -> list[BruleRecord]:
    filters = [BruleRecord.tenant_id == tenant_id]
    if plot_id is not None:
        filters.append(BruleRecord.plot_id == plot_id)
    if plant_id is not None:
        filters.append(BruleRecord.plant_id == plant_id)
    if campaign is not None:
        start = datetime.date(campaign, 5, 1)
        end = datetime.date(campaign + 1, 5, 1)
        filters.extend(
            [BruleRecord.record_date >= start, BruleRecord.record_date < end]
        )
    stmt = (
        select(BruleRecord)
        .where(*filters)
        .options(selectinload(BruleRecord.plant), selectinload(BruleRecord.plot))
        .order_by(BruleRecord.record_date.desc())
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_brule_record(
    db: AsyncSession,
    record_id: int,
    tenant_id: int,
) -> Optional[BruleRecord]:
    res = await db.execute(
        select(BruleRecord).where(
            BruleRecord.id == record_id,
            BruleRecord.tenant_id == tenant_id,
        )
    )
    return res.scalar_one_or_none()


async def create_brule_record(
    db: AsyncSession,
    *,
    tenant_id: int,
    plant_id: int,
    plot_id: int,
    record_date: datetime.date,
    diameter_cm: int,
    user_id: Optional[int] = None,
) -> BruleRecord:
    record = BruleRecord(
        tenant_id=tenant_id,
        created_by_user_id=user_id,
        plant_id=plant_id,
        plot_id=plot_id,
        record_date=record_date,
        diameter_cm=diameter_cm,
    )
    db.add(record)
    await db.flush()
    return record


async def update_brule_record(
    db: AsyncSession,
    record_id: int,
    tenant_id: int,
    *,
    diameter_cm: int,
) -> Optional[BruleRecord]:
    record = await get_brule_record(db, record_id, tenant_id)
    if record is None:
        return None
    record.diameter_cm = diameter_cm
    await db.flush()
    return record


async def delete_brule_record(
    db: AsyncSession,
    record_id: int,
    tenant_id: int,
) -> None:
    record = await get_brule_record(db, record_id, tenant_id)
    if record is not None:
        await db.delete(record)
        await db.flush()


async def get_brule_evolution(
    db: AsyncSession,
    tenant_id: int,
    plant_id: int,
) -> list[tuple[datetime.date, int]]:
    """Return (record_date, diameter_cm) ordered ASC for Chart.js line chart."""
    res = await db.execute(
        select(BruleRecord.record_date, BruleRecord.diameter_cm)
        .where(
            BruleRecord.tenant_id == tenant_id,
            BruleRecord.plant_id == plant_id,
        )
        .order_by(BruleRecord.record_date.asc())
    )
    return [(row.record_date, row.diameter_cm) for row in res.all()]


async def get_last_brule_by_plant(
    db: AsyncSession,
    tenant_id: int,
    plot_id: int,
) -> dict[int, int]:
    """Return {plant_id: diameter_cm} for the most recent record per plant in a plot."""
    sq = (
        select(
            BruleRecord.plant_id,
            func.max(BruleRecord.record_date).label("last_date"),
        )
        .where(BruleRecord.tenant_id == tenant_id, BruleRecord.plot_id == plot_id)
        .group_by(BruleRecord.plant_id)
        .subquery()
    )
    stmt = (
        select(BruleRecord.plant_id, BruleRecord.diameter_cm)
        .join(
            sq,
            and_(
                BruleRecord.plant_id == sq.c.plant_id,
                BruleRecord.record_date == sq.c.last_date,
            ),
        )
        .where(BruleRecord.tenant_id == tenant_id, BruleRecord.plot_id == plot_id)
    )
    res = await db.execute(stmt)
    return {row.plant_id: row.diameter_cm for row in res.all()}


async def get_brule_production_correlation(
    db: AsyncSession,
    tenant_id: int,
    *,
    plot_id: Optional[int] = None,
    campaign: Optional[int] = None,
) -> list[dict]:
    """Return plants with both brulé records and truffle production in the campaign.

    Each item: plant_id, plant_label, plot_label, last_diameter_cm, total_weight_kg.
    """
    from app.models.plant import Plant
    from app.models.plot import Plot
    from app.models.truffle_event import TruffleEvent

    # Step 1: get last brulé diameter per plant (+ labels)
    brule_filters = [BruleRecord.tenant_id == tenant_id]
    if plot_id is not None:
        brule_filters.append(BruleRecord.plot_id == plot_id)

    sq_last = (
        select(
            BruleRecord.plant_id,
            func.max(BruleRecord.record_date).label("last_date"),
        )
        .where(*brule_filters)
        .group_by(BruleRecord.plant_id)
        .subquery()
    )
    brule_stmt = (
        select(
            BruleRecord.plant_id,
            BruleRecord.diameter_cm,
            Plant.label.label("plant_label"),
            Plot.name.label("plot_name"),
        )
        .join(
            sq_last,
            and_(
                BruleRecord.plant_id == sq_last.c.plant_id,
                BruleRecord.record_date == sq_last.c.last_date,
            ),
        )
        .join(Plant, BruleRecord.plant_id == Plant.id)
        .join(Plot, BruleRecord.plot_id == Plot.id)
        .where(*brule_filters)
    )
    brule_res = await db.execute(brule_stmt)
    brule_rows = brule_res.all()
    if not brule_rows:
        return []
    brule_data = {row.plant_id: row for row in brule_rows}

    # Step 2: get production per plant from TruffleEvent
    prod_filters = [
        TruffleEvent.tenant_id == tenant_id,
        TruffleEvent.undone_at.is_(None),
        TruffleEvent.plant_id.in_(list(brule_data.keys())),
    ]
    if plot_id is not None:
        prod_filters.append(TruffleEvent.plot_id == plot_id)
    if campaign is not None:
        start_dt = datetime.datetime(campaign, 4, 1, tzinfo=datetime.timezone.utc)
        end_dt = datetime.datetime(campaign + 1, 4, 1, tzinfo=datetime.timezone.utc)
        prod_filters.extend(
            [TruffleEvent.created_at >= start_dt, TruffleEvent.created_at < end_dt]
        )

    prod_stmt = (
        select(
            TruffleEvent.plant_id,
            func.sum(TruffleEvent.estimated_weight_grams).label("total_grams"),
        )
        .where(*prod_filters)
        .group_by(TruffleEvent.plant_id)
    )
    prod_res = await db.execute(prod_stmt)
    prod_data = {row.plant_id: float(row.total_grams) for row in prod_res.all()}

    # Step 3: merge — only plants with both brulé records and production
    result_rows = []
    for plant_id, brule_row in brule_data.items():
        if plant_id not in prod_data:
            continue
        result_rows.append(
            {
                "plant_id": plant_id,
                "plant_label": brule_row.plant_label,
                "plot_label": brule_row.plot_name,
                "last_diameter_cm": brule_row.diameter_cm,
                "total_weight_kg": round(prod_data[plant_id] / 1000, 3),
            }
        )
    result_rows.sort(key=lambda r: r["last_diameter_cm"], reverse=True)
    return result_rows

from __future__ import annotations

import csv
import datetime
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.models.well import Well
from app.utils import format_eu


def _format_date(d: datetime.date) -> str:
    return d.strftime("%d/%m/%Y")


def _format_num(val: float, decimals: int = 2) -> str:
    return format_eu(val, decimals)


async def _load_plots_by_id(db: AsyncSession, user_id: int) -> dict[int, str]:
    result = await db.execute(select(Plot).where(Plot.user_id == user_id))
    return {p.id: p.name for p in result.scalars().all()}


async def export_plots_csv(db: AsyncSession, user_id: int) -> bytes:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    plots = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    for p in plots:
        writer.writerow(
            [
                p.name,
                _format_date(p.planting_date),
                p.polygon or "",
                p.plot_num or "",
                p.cadastral_ref or "",
                p.hydrant or "",
                p.sector or "",
                p.num_plants if p.num_plants is not None else "",
                _format_num(p.area_ha, 4) if p.area_ha is not None else "",
                _format_date(p.production_start) if p.production_start else "",
                "1" if p.has_irrigation else "0",
            ]
        )
    return buf.getvalue().encode("utf-8")


async def export_expenses_csv(db: AsyncSession, user_id: int) -> bytes:
    plots_by_id = await _load_plots_by_id(db, user_id)
    result = await db.execute(
        select(Expense).where(Expense.user_id == user_id).order_by(Expense.date)
    )
    expenses = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    for e in expenses:
        writer.writerow(
            [
                _format_date(e.date),
                e.description or "",
                e.person or "",
                plots_by_id.get(e.plot_id, "") if e.plot_id is not None else "",
                _format_num(e.amount, 2),
                e.category or "",
            ]
        )
    return buf.getvalue().encode("utf-8")


async def export_incomes_csv(db: AsyncSession, user_id: int) -> bytes:
    plots_by_id = await _load_plots_by_id(db, user_id)
    result = await db.execute(
        select(Income).where(Income.user_id == user_id).order_by(Income.date)
    )
    incomes = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    for inc in incomes:
        writer.writerow(
            [
                _format_date(inc.date),
                plots_by_id.get(inc.plot_id, "") if inc.plot_id is not None else "",
                _format_num(inc.amount_kg, 3),
                inc.category or "",
                _format_num(inc.euros_per_kg, 2),
            ]
        )
    return buf.getvalue().encode("utf-8")


async def export_irrigation_csv(db: AsyncSession, user_id: int) -> bytes:
    plots_by_id = await _load_plots_by_id(db, user_id)
    result = await db.execute(
        select(IrrigationRecord)
        .where(IrrigationRecord.user_id == user_id)
        .order_by(IrrigationRecord.date)
    )
    records = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    for r in records:
        writer.writerow(
            [
                _format_date(r.date),
                plots_by_id.get(r.plot_id, ""),
                _format_num(r.water_m3, 3),
                r.notes or "",
            ]
        )
    return buf.getvalue().encode("utf-8")


async def export_wells_csv(db: AsyncSession, user_id: int) -> bytes:
    plots_by_id = await _load_plots_by_id(db, user_id)
    result = await db.execute(
        select(Well).where(Well.user_id == user_id).order_by(Well.date)
    )
    records = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    for r in records:
        writer.writerow(
            [
                _format_date(r.date),
                plots_by_id.get(r.plot_id, ""),
                r.wells_per_plant,
                r.notes or "",
            ]
        )
    return buf.getvalue().encode("utf-8")

from __future__ import annotations

import csv
import datetime
import io
import zipfile
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.truffle_event import TruffleEvent
from app.models.well import Well
from app.utils import format_eu, format_sparse_row_config


def _format_date(d: datetime.date) -> str:
    return d.strftime("%d/%m/%Y")


def _format_num(val: float, decimals: int = 2) -> str:
    return format_eu(val, decimals)


async def _load_plots_by_id(db: AsyncSession, user_id: int) -> dict[int, str]:
    result = await db.execute(select(Plot).where(Plot.user_id == user_id))
    return {p.id: p.name for p in result.scalars().all()}


async def _load_row_config_by_plot(db: AsyncSession, user_id: int) -> dict[int, str]:
    result = await db.execute(
        select(Plant)
        .where(Plant.user_id == user_id)
        .order_by(Plant.plot_id, Plant.row_order, Plant.visual_col)
    )
    plants = result.scalars().all()

    by_plot_row_cols: dict[int, dict[int, list[int]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for p in plants:
        by_plot_row_cols[p.plot_id][p.row_order].append(p.visual_col)

    row_config_by_plot: dict[int, str] = {}
    for plot_id, rows_dict in by_plot_row_cols.items():
        row_columns = [sorted(rows_dict[idx]) for idx in sorted(rows_dict)]
        row_config_by_plot[plot_id] = format_sparse_row_config(row_columns)
    return row_config_by_plot


async def export_plots_csv(db: AsyncSession, user_id: int) -> bytes:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    plots = result.scalars().all()
    row_config_by_plot = await _load_row_config_by_plot(db, user_id)

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
                row_config_by_plot.get(p.id, ""),
                p.recinto or "1",
                _format_num(p.caudal_riego, 2) if p.caudal_riego is not None else "",
                p.provincia_cod or "",
                p.municipio_cod or "",
            ]
        )
    return buf.getvalue().encode("utf-8")


async def export_truffles_csv(db: AsyncSession, user_id: int) -> bytes:
    result = await db.execute(
        select(TruffleEvent)
        .options(
            selectinload(TruffleEvent.plot),
            selectinload(TruffleEvent.plant),
        )
        .where(
            TruffleEvent.user_id == user_id,
            TruffleEvent.undone_at.is_(None),
        )
        .order_by(TruffleEvent.created_at)
    )
    events = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    for e in events:
        created = e.created_at
        if created.tzinfo is not None:
            created = created.astimezone(datetime.timezone.utc)
        writer.writerow(
            [
                created.strftime("%d/%m/%Y %H:%M:%S"),
                e.plot.name if e.plot else "",
                e.plant.label if e.plant else "",
                _format_num(e.estimated_weight_grams or 0.0, 1),
                e.source or "manual",
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


async def export_plot_events_csv(db: AsyncSession, user_id: int) -> bytes:
    plots_by_id = await _load_plots_by_id(db, user_id)
    result = await db.execute(
        select(PlotEvent)
        .where(
            PlotEvent.user_id == user_id,
            PlotEvent.related_irrigation_id.is_(None),
            PlotEvent.related_well_id.is_(None),
        )
        .order_by(PlotEvent.date)
    )
    events = result.scalars().all()

    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";", lineterminator="\n")
    for e in events:
        writer.writerow(
            [
                _format_date(e.date),
                plots_by_id.get(e.plot_id, ""),
                e.event_type,
                e.notes or "",
                "1" if e.is_recurring else "0",
            ]
        )
    return buf.getvalue().encode("utf-8")


async def export_all_csv_zip(db: AsyncSession, user_id: int) -> bytes:
    files = [
        ("parcelas.csv", await export_plots_csv(db, user_id)),
        ("gastos.csv", await export_expenses_csv(db, user_id)),
        ("ingresos.csv", await export_incomes_csv(db, user_id)),
        ("riego.csv", await export_irrigation_csv(db, user_id)),
        ("pozos.csv", await export_wells_csv(db, user_id)),
        ("produccion.csv", await export_truffles_csv(db, user_id)),
        ("labores.csv", await export_plot_events_csv(db, user_id)),
    ]

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for filename, content in files:
            zf.writestr(filename, content)

    return zip_buffer.getvalue()

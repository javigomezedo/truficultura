from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from datetime import timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plant import Plant
from app.models.plot import Plot
from app.models.truffle_event import TruffleEvent
from app.services.plots_service import _recalculate_percentages
from app.utils import generate_plant_labels, row_label_from_index


@dataclass
class PlantCell:
    plant: Plant
    campaign_count: int
    total_count: int


@dataclass
class MapRow:
    row_label: str
    row_order: int
    cells: list[PlantCell] = field(default_factory=list)


async def list_plants(db: AsyncSession, plot_id: int, user_id: int) -> list[Plant]:
    res = await db.execute(
        select(Plant)
        .where(Plant.plot_id == plot_id, Plant.user_id == user_id)
        .order_by(Plant.row_order, Plant.col_order)
    )
    return res.scalars().all()


async def get_plant(db: AsyncSession, plant_id: int, user_id: int) -> Optional[Plant]:
    res = await db.execute(
        select(Plant).where(Plant.id == plant_id, Plant.user_id == user_id)
    )
    return res.scalar_one_or_none()


async def has_active_truffle_events(
    db: AsyncSession, plot_id: int, user_id: int
) -> bool:
    """Return True if there is at least one active (non-undone) truffle event for a plot."""
    res = await db.execute(
        select(TruffleEvent.id)
        .where(
            TruffleEvent.plot_id == plot_id,
            TruffleEvent.user_id == user_id,
            TruffleEvent.undone_at.is_(None),
        )
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def configure_plot_map(
    db: AsyncSession,
    plot: Plot,
    *,
    user_id: int,
    row_counts: list[int],
) -> list[Plant]:
    """Replace the plant layout of a plot.

    Raises ValueError if active truffle events already exist (data protection).
    Updates plot.num_plants once the new layout is saved.
    """
    if await has_active_truffle_events(db, plot.id, user_id):
        raise ValueError(
            "No se puede regenerar el mapa: existen registros de trufas activos."
        )

    # Remove all current plants (cascade deletes any orphan truffle_events)
    await db.execute(
        delete(Plant).where(Plant.plot_id == plot.id, Plant.user_id == user_id)
    )
    await db.flush()

    grid = generate_plant_labels(row_counts)
    plants: list[Plant] = []
    for row_idx, labels in enumerate(grid):
        row_label = row_label_from_index(row_idx)
        for col_idx, label in enumerate(labels):
            p = Plant(
                plot_id=plot.id,
                user_id=user_id,
                label=label,
                row_label=row_label,
                row_order=row_idx,
                col_order=col_idx,
            )
            db.add(p)
            plants.append(p)

    plot.num_plants = sum(row_counts)
    await db.flush()
    await _recalculate_percentages(db, user_id)
    return plants


def _campaign_date_range(
    cy: int,
) -> tuple[datetime.datetime, datetime.datetime]:
    """Return [start, end) UTC datetime range for campaign year cy."""
    start = datetime.datetime(cy, 4, 1, tzinfo=timezone.utc)
    end = datetime.datetime(cy + 1, 4, 1, tzinfo=timezone.utc)
    return start, end


async def get_plot_map_context(
    db: AsyncSession,
    plot: Plot,
    *,
    user_id: int,
    selected_campaign: Optional[int],
) -> dict:
    """Build the template context for the plant map view.

    Returns a dict with:
      - rows: list[MapRow]
      - selected_campaign: int | None
      - has_plants: bool
    """
    plants_res = await db.execute(
        select(Plant)
        .where(Plant.plot_id == plot.id, Plant.user_id == user_id)
        .order_by(Plant.row_order, Plant.col_order)
    )
    all_plants: list[Plant] = plants_res.scalars().all()

    if not all_plants:
        return {"rows": [], "selected_campaign": selected_campaign, "has_plants": False}

    base_filters = [
        TruffleEvent.plot_id == plot.id,
        TruffleEvent.user_id == user_id,
        TruffleEvent.undone_at.is_(None),
    ]

    # Historical totals
    total_q = (
        select(TruffleEvent.plant_id, func.count(TruffleEvent.id).label("cnt"))
        .where(*base_filters)
        .group_by(TruffleEvent.plant_id)
    )
    total_res = await db.execute(total_q)
    total_by_plant: dict[int, int] = {row.plant_id: row.cnt for row in total_res.all()}

    # Campaign counts
    campaign_by_plant: dict[int, int] = {}
    if selected_campaign is not None:
        start, end = _campaign_date_range(selected_campaign)
        campaign_q = (
            select(TruffleEvent.plant_id, func.count(TruffleEvent.id).label("cnt"))
            .where(
                *base_filters,
                TruffleEvent.created_at >= start,
                TruffleEvent.created_at < end,
            )
            .group_by(TruffleEvent.plant_id)
        )
        campaign_res = await db.execute(campaign_q)
        campaign_by_plant = {row.plant_id: row.cnt for row in campaign_res.all()}

    rows: list[MapRow] = []
    current_row: Optional[MapRow] = None
    for plant in all_plants:
        if current_row is None or current_row.row_order != plant.row_order:
            current_row = MapRow(row_label=plant.row_label, row_order=plant.row_order)
            rows.append(current_row)
        current_row.cells.append(
            PlantCell(
                plant=plant,
                campaign_count=campaign_by_plant.get(plant.id, 0),
                total_count=total_by_plant.get(plant.id, 0),
            )
        )

    return {"rows": rows, "selected_campaign": selected_campaign, "has_plants": True}

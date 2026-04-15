from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from datetime import timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.truffle_event import TruffleEvent
from app.utils import row_label_from_index


@dataclass
class PlantCell:
    plant: Optional[Plant]
    visual_col: int
    campaign_weight_grams: float
    total_weight_grams: float


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
    row_columns: list[list[int]],
) -> list[Plant]:
    """Replace the plant layout of a plot.

    Raises ValueError if active truffle events already exist (data protection).
    Does NOT modify plot.num_plants — that field is managed via the plot form only.
    """
    if await has_active_truffle_events(db, plot.id, user_id):
        raise ValueError(
            _("No se puede regenerar el mapa: existen registros de trufas activos.")
        )

    # Remove all current plants (cascade deletes any orphan truffle_events)
    await db.execute(
        delete(Plant).where(Plant.plot_id == plot.id, Plant.user_id == user_id)
    )
    await db.flush()

    plants: list[Plant] = []
    for row_idx, columns in enumerate(row_columns):
        row_label = row_label_from_index(row_idx)
        for visual_col in sorted(set(columns)):
            p = Plant(
                plot_id=plot.id,
                user_id=user_id,
                label=f"{row_label}{visual_col}",
                row_label=row_label,
                row_order=row_idx,
                col_order=visual_col - 1,
                visual_col=visual_col,
            )
            db.add(p)
            plants.append(p)

    await db.flush()
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
        select(
            TruffleEvent.plant_id,
            func.sum(func.coalesce(TruffleEvent.estimated_weight_grams, 1.0)).label(
                "total_grams"
            ),
        )
        .where(*base_filters)
        .group_by(TruffleEvent.plant_id)
    )
    total_res = await db.execute(total_q)
    total_by_plant: dict[int, float] = {
        row.plant_id: round(float(row.total_grams or 0.0), 2) for row in total_res.all()
    }

    # Campaign counts
    campaign_by_plant: dict[int, float] = {}
    if selected_campaign is not None:
        start, end = _campaign_date_range(selected_campaign)
        campaign_q = (
            select(
                TruffleEvent.plant_id,
                func.sum(func.coalesce(TruffleEvent.estimated_weight_grams, 1.0)).label(
                    "total_grams"
                ),
            )
            .where(
                *base_filters,
                TruffleEvent.created_at >= start,
                TruffleEvent.created_at < end,
            )
            .group_by(TruffleEvent.plant_id)
        )
        campaign_res = await db.execute(campaign_q)
        campaign_by_plant = {
            row.plant_id: round(float(row.total_grams or 0.0), 2)
            for row in campaign_res.all()
        }

    rows: list[MapRow] = []
    by_row: dict[int, list[Plant]] = {}
    for plant in all_plants:
        by_row.setdefault(plant.row_order, []).append(plant)

    for row_order in sorted(by_row):
        row_plants = sorted(by_row[row_order], key=lambda p: p.col_order)
        row = MapRow(row_label=row_plants[0].row_label, row_order=row_order)
        by_visual_col = {
            (
                p.visual_col
                if getattr(p, "visual_col", None) is not None
                else p.col_order + 1
            ): p
            for p in row_plants
        }
        max_col = max(by_visual_col)

        for visual_col in range(1, max_col + 1):
            plant = by_visual_col.get(visual_col)
            if plant is None:
                row.cells.append(
                    PlantCell(
                        plant=None,
                        visual_col=visual_col,
                        campaign_weight_grams=0.0,
                        total_weight_grams=0.0,
                    )
                )
                continue

            row.cells.append(
                PlantCell(
                    plant=plant,
                    visual_col=visual_col,
                    campaign_weight_grams=campaign_by_plant.get(plant.id, 0.0),
                    total_weight_grams=total_by_plant.get(plant.id, 0.0),
                )
            )

        rows.append(row)

    return {"rows": rows, "selected_campaign": selected_campaign, "has_plants": True}

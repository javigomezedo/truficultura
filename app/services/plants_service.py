from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from datetime import timezone
from typing import Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.plant import Plant, HostSpecies, PlantStatus
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


async def list_plants(db: AsyncSession, plot_id: int, tenant_id: int) -> list[Plant]:
    res = await db.execute(
        select(Plant)
        .where(Plant.plot_id == plot_id, Plant.tenant_id == tenant_id)
        .order_by(Plant.row_order, Plant.col_order)
    )
    return res.scalars().all()


async def get_plant(db: AsyncSession, plant_id: int, tenant_id: int) -> Optional[Plant]:
    res = await db.execute(
        select(Plant).where(Plant.id == plant_id, Plant.tenant_id == tenant_id)
    )
    return res.scalar_one_or_none()


async def update_plant_status(
    db: AsyncSession,
    plant_id: int,
    tenant_id: int,
    *,
    status: PlantStatus,
    baja_date: Optional[datetime.date],
) -> Optional[Plant]:
    """Update the health status and optional baja_date of a plant.

    Returns the updated plant, or None if the plant does not belong to the tenant.
    """
    plant = await get_plant(db, plant_id, tenant_id)
    if plant is None:
        return None
    plant.status = status
    plant.baja_date = baja_date
    await db.flush()
    return plant


async def update_plant_species(
    db: AsyncSession,
    plant_id: int,
    tenant_id: int,
    *,
    host_species: Optional[HostSpecies],
) -> Optional[Plant]:
    """Update the host species of a plant.

    Returns the updated plant, or None if the plant does not belong to the tenant.
    """
    plant = await get_plant(db, plant_id, tenant_id)
    if plant is None:
        return None
    plant.host_species = host_species
    await db.flush()
    return plant


async def get_species_summary(
    db: AsyncSession,
    plot_id: int,
    tenant_id: int,
    *,
    selected_campaign: Optional[int],
) -> list[dict]:
    """Return kg/plant aggregated by host species for the given plot and campaign.

    Each entry: {species, num_plants, total_grams, grams_per_plant}
    """
    base_filters = [
        TruffleEvent.plot_id == plot_id,
        TruffleEvent.tenant_id == tenant_id,
        TruffleEvent.undone_at.is_(None),
    ]
    if selected_campaign is not None:
        start, end = _campaign_date_range(selected_campaign)
        base_filters += [
            TruffleEvent.created_at >= start,
            TruffleEvent.created_at < end,
        ]

    q = (
        select(
            Plant.host_species,
            func.count(Plant.id.distinct()).label("num_plants"),
            func.sum(func.coalesce(TruffleEvent.estimated_weight_grams, 1.0)).label("total_grams"),
        )
        .join(Plant, TruffleEvent.plant_id == Plant.id)
        .where(*base_filters)
        .group_by(Plant.host_species)
    )
    res = await db.execute(q)
    rows = []
    for row in res.all():
        total_g = float(row.total_grams or 0.0)
        n = row.num_plants or 0
        rows.append(
            {
                "species": row.host_species,
                "num_plants": n,
                "total_grams": round(total_g, 1),
                "grams_per_plant": round(total_g / n, 1) if n else 0.0,
            }
        )
    rows.sort(key=lambda r: (r["species"] is None, str(r["species"])))
    return rows


async def has_active_truffle_events(
    db: AsyncSession, plot_id: int, tenant_id: int
) -> bool:
    """Return True if there is at least one active (non-undone) truffle event for a plot."""
    res = await db.execute(
        select(TruffleEvent.id)
        .where(
            TruffleEvent.plot_id == plot_id,
            TruffleEvent.tenant_id == tenant_id,
            TruffleEvent.undone_at.is_(None),
        )
        .limit(1)
    )
    return res.scalar_one_or_none() is not None


async def configure_plot_map(
    db: AsyncSession,
    plot: Plot,
    *,
    tenant_id: int,
    acting_user_id: Optional[int] = None,
    row_columns: list[list[int]],
    plant_limit: Optional[int] = None,
) -> list[Plant]:
    """Replace the plant layout of a plot.

    Raises ValueError if active truffle events already exist (data protection).
    Raises PlantLimitExceededException if the new map would exceed the plan limit.
    Does NOT modify plot.num_plants — that field is managed via the plot form only.
    """
    if await has_active_truffle_events(db, plot.id, tenant_id):
        raise ValueError(
            _("No se puede regenerar el mapa: existen registros de trufas activos.")
        )

    # Check plant limit: count plants from the new config and compare against
    # effective total of OTHER plots (current plot's old plants will be deleted).
    if plant_limit is not None:
        new_plant_count = sum(len(set(cols)) for cols in row_columns)
        from app.services.plots_service import _get_effective_plant_total
        other_total = await _get_effective_plant_total(
            db, tenant_id, exclude_plot_id=plot.id
        )
        if other_total + new_plant_count > plant_limit:
            from app.plan_access import PlantLimitExceededException
            raise PlantLimitExceededException(plant_limit)

    # Save per-label species before deleting (to restore individual assignments)
    existing_res = await db.execute(
        select(Plant.label, Plant.host_species).where(
            Plant.plot_id == plot.id,
            Plant.tenant_id == tenant_id,
            Plant.host_species.is_not(None),
        )
    )
    species_by_label: dict[str, object] = {
        row.label: row.host_species for row in existing_res.all()
    }

    # Remove all current plants (cascade deletes any orphan truffle_events)
    await db.execute(
        delete(Plant).where(Plant.plot_id == plot.id, Plant.tenant_id == tenant_id)
    )
    await db.flush()

    plants: list[Plant] = []
    for row_idx, columns in enumerate(row_columns):
        row_label = row_label_from_index(row_idx)
        for visual_col in sorted(set(columns)):
            label = f"{row_label}{visual_col}"
            p = Plant(
                plot_id=plot.id,
                tenant_id=tenant_id,
                created_by_user_id=acting_user_id,
                label=label,
                row_label=row_label,
                row_order=row_idx,
                col_order=visual_col - 1,
                visual_col=visual_col,
                host_species=species_by_label.get(label, plot.default_host_species),
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
    tenant_id: int,
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
        .where(Plant.plot_id == plot.id, Plant.tenant_id == tenant_id)
        .order_by(Plant.row_order, Plant.col_order)
    )
    all_plants: list[Plant] = plants_res.scalars().all()

    if not all_plants:
        return {"rows": [], "selected_campaign": selected_campaign, "has_plants": False}

    base_filters = [
        TruffleEvent.plot_id == plot.id,
        TruffleEvent.tenant_id == tenant_id,
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

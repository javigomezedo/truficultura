from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import random
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.truffle_event import TruffleEvent
from app.models.user import User
from app.utils import row_label_from_index


@dataclass
class SeedSummary:
    user_id: int
    username: str
    created_plots: int = 0
    created_plants: int = 0
    created_events: int = 0
    campaigns: int = 0


def _campaign_bounds(campaign_year: int) -> tuple[dt.datetime, dt.datetime]:
    start = dt.datetime(campaign_year, 4, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
    end = dt.datetime(campaign_year + 1, 4, 1, 0, 0, 0, tzinfo=dt.timezone.utc)
    return start, end


def _random_dt_in_campaign(rng: random.Random, campaign_year: int) -> dt.datetime:
    start, end = _campaign_bounds(campaign_year)
    span_seconds = int((end - start).total_seconds())
    return start + dt.timedelta(seconds=rng.randint(0, span_seconds - 1))


def _build_sparse_row_columns(
    rng: random.Random,
    rows_min: int,
    rows_max: int,
    cols_min: int,
    cols_max: int,
) -> list[list[int]]:
    row_count = rng.randint(rows_min, rows_max)
    row_columns: list[list[int]] = []
    for _ in range(row_count):
        max_col = rng.randint(cols_min, cols_max)
        all_cols = list(range(1, max_col + 1))
        # Keep between 65% and 100% of columns to produce realistic sparse rows.
        keep_n = max(1, int(len(all_cols) * rng.uniform(0.65, 1.0)))
        chosen = sorted(rng.sample(all_cols, k=keep_n))
        row_columns.append(chosen)
    return row_columns


def _make_plants_for_plot(
    *,
    rng: random.Random,
    user_id: int,
    plot_id: int,
    row_columns: Sequence[Sequence[int]],
) -> list[Plant]:
    plants: list[Plant] = []
    for row_idx, cols in enumerate(row_columns):
        row_label = row_label_from_index(row_idx)
        for visual_col in sorted(set(cols)):
            plants.append(
                Plant(
                    user_id=user_id,
                    plot_id=plot_id,
                    label=f"{row_label}{visual_col}",
                    row_label=row_label,
                    row_order=row_idx,
                    col_order=visual_col - 1,
                    visual_col=visual_col,
                )
            )
    rng.shuffle(plants)
    return plants


def _make_truffle_events(
    *,
    rng: random.Random,
    user_id: int,
    plot_id: int,
    plants: Sequence[Plant],
    campaign_year: int,
    min_events: int,
    max_events: int,
) -> list[TruffleEvent]:
    event_count = rng.randint(min_events, max_events)
    events: list[TruffleEvent] = []

    for _ in range(event_count):
        plant = rng.choice(plants)
        created_at = _random_dt_in_campaign(rng, campaign_year)
        undone_at = None
        # Keep some historical undos so filters and totals can be tested.
        if rng.random() < 0.12:
            undone_at = created_at + dt.timedelta(seconds=rng.randint(8, 180))

        events.append(
            TruffleEvent(
                user_id=user_id,
                plot_id=plot_id,
                plant_id=plant.id,
                source="qr" if rng.random() < 0.55 else "manual",
                created_at=created_at,
                undo_window_expires_at=created_at + dt.timedelta(seconds=30),
                undone_at=undone_at,
            )
        )

    return events


async def _resolve_user(session, user_id: int | None) -> User:
    if user_id is not None:
        res = await session.execute(select(User).where(User.id == user_id))
        user = res.scalar_one_or_none()
        if user is None:
            raise ValueError(f"No existe usuario con id={user_id}")
        return user

    res = await session.execute(select(User).order_by(User.id.asc()).limit(1))
    user = res.scalar_one_or_none()
    if user is None:
        raise ValueError("No hay usuarios en la base de datos")
    return user


async def seed_data(args: argparse.Namespace) -> SeedSummary:
    rng = random.Random(args.seed)

    async with AsyncSessionLocal() as session:
        user = await _resolve_user(session, args.user_id)

        summary = SeedSummary(user_id=user.id, username=user.username)

        # Names include a run token to avoid collisions when seeding multiple times.
        run_token = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")

        new_plots: list[Plot] = []
        for idx in range(1, args.plots + 1):
            row_columns = _build_sparse_row_columns(
                rng,
                rows_min=args.rows_min,
                rows_max=args.rows_max,
                cols_min=args.cols_min,
                cols_max=args.cols_max,
            )
            plant_count = sum(len(set(cols)) for cols in row_columns)

            plot = Plot(
                user_id=user.id,
                name=f"Demo {run_token} - Parcela {idx}",
                polygon=str(rng.randint(1, 30)),
                plot_num=str(rng.randint(1, 999)),
                cadastral_ref=f"DEMO{run_token}{idx:03d}",
                hydrant=f"H-{rng.randint(1, 12):02d}",
                sector=f"S{rng.randint(1, 6)}",
                num_plants=plant_count,
                planting_date=dt.date(
                    rng.randint(2016, 2023), rng.randint(1, 12), rng.randint(1, 28)
                ),
                area_ha=round(rng.uniform(0.6, 3.5), 4),
                production_start=dt.date(
                    rng.randint(2022, 2026), rng.randint(1, 12), rng.randint(1, 28)
                ),
                percentage=0.0,
                has_irrigation=rng.random() < 0.8,
            )
            session.add(plot)
            await session.flush()

            plants = _make_plants_for_plot(
                rng=rng,
                user_id=user.id,
                plot_id=plot.id,
                row_columns=row_columns,
            )
            session.add_all(plants)
            await session.flush()

            summary.created_plots += 1
            summary.created_plants += len(plants)

            campaign_years = list(range(args.start_campaign, args.end_campaign + 1))
            summary.campaigns = len(campaign_years)
            for campaign_year in campaign_years:
                events = _make_truffle_events(
                    rng=rng,
                    user_id=user.id,
                    plot_id=plot.id,
                    plants=plants,
                    campaign_year=campaign_year,
                    min_events=args.events_min,
                    max_events=args.events_max,
                )
                session.add_all(events)
                summary.created_events += len(events)

            new_plots.append(plot)

        # Keep percentages coherent with declared plant counts.
        if new_plots:
            all_plots_res = await session.execute(
                select(Plot).where(Plot.user_id == user.id)
            )
            all_plots = all_plots_res.scalars().all()
            total_plants = sum(p.num_plants or 0 for p in all_plots)
            for p in all_plots:
                p.percentage = (
                    ((p.num_plants or 0) / total_plants * 100.0)
                    if total_plants
                    else 0.0
                )

        await session.commit()
        return summary


def _build_parser() -> argparse.ArgumentParser:
    current_campaign = (
        dt.date.today().year if dt.date.today().month >= 4 else dt.date.today().year - 1
    )

    parser = argparse.ArgumentParser(
        description="Genera datos demo de parcelas/mapas/eventos de trufa para pruebas manuales."
    )
    parser.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="Usuario destino (por defecto: primer usuario)",
    )
    parser.add_argument(
        "--plots", type=int, default=4, help="Numero de parcelas demo a crear"
    )
    parser.add_argument(
        "--start-campaign",
        type=int,
        default=current_campaign - 5,
        help="Campana inicial (anio de inicio)",
    )
    parser.add_argument(
        "--end-campaign",
        type=int,
        default=current_campaign,
        help="Campana final (anio de inicio)",
    )
    parser.add_argument(
        "--events-min",
        type=int,
        default=25,
        help="Minimo de eventos por parcela y campana",
    )
    parser.add_argument(
        "--events-max",
        type=int,
        default=120,
        help="Maximo de eventos por parcela y campana",
    )
    parser.add_argument(
        "--rows-min", type=int, default=4, help="Filas minimas por mapa"
    )
    parser.add_argument(
        "--rows-max", type=int, default=8, help="Filas maximas por mapa"
    )
    parser.add_argument(
        "--cols-min", type=int, default=5, help="Columnas minimas potenciales por fila"
    )
    parser.add_argument(
        "--cols-max", type=int, default=14, help="Columnas maximas potenciales por fila"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Semilla para datos reproducibles"
    )
    return parser


def _validate_args(args: argparse.Namespace) -> None:
    if args.plots <= 0:
        raise ValueError("--plots debe ser > 0")
    if args.start_campaign > args.end_campaign:
        raise ValueError("--start-campaign no puede ser mayor que --end-campaign")
    if (
        args.events_min <= 0
        or args.events_max <= 0
        or args.events_min > args.events_max
    ):
        raise ValueError("Rango de eventos invalido")
    if args.rows_min <= 0 or args.rows_max <= 0 or args.rows_min > args.rows_max:
        raise ValueError("Rango de filas invalido")
    if args.cols_min <= 0 or args.cols_max <= 0 or args.cols_min > args.cols_max:
        raise ValueError("Rango de columnas invalido")


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    _validate_args(args)
    summary = asyncio.run(seed_data(args))
    print("Seed completado")
    print(f"Usuario: {summary.user_id} ({summary.username})")
    print(f"Parcelas creadas: {summary.created_plots}")
    print(f"Plantas creadas: {summary.created_plants}")
    print(f"Campanas generadas: {summary.campaigns}")
    print(f"Eventos de trufa creados: {summary.created_events}")


if __name__ == "__main__":
    main()

"""
seed_full_demo.py — Genera un dataset completo y realista de demo.

Incluye: parcelas, plantas, eventos de trufa, ingresos (por venta de trufa),
gastos (por categoría, asignados y generales), pozos y registros de riego.

Uso:
    .venv/bin/python scripts/seed_full_demo.py
    .venv/bin/python scripts/seed_full_demo.py --user-id 1 --seed 99
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import random
from dataclasses import dataclass, field

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.expense import Expense
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plant import Plant
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.truffle_event import TruffleEvent
from app.models.user import User
from app.models.well import Well
from app.schemas.plot_event import EventType
from app.utils import campaign_label, row_label_from_index

# ---------------------------------------------------------------------------
# Realistic plot definitions (name, area_ha, num_rows, cols_per_row range)
# ---------------------------------------------------------------------------
PLOT_SPECS = [
    ("Carrascal Norte", 2.40, 8, (8, 12)),
    ("Carrascal Sur", 1.85, 6, (7, 11)),
    ("Robledal A", 3.10, 10, (9, 14)),
    ("Robledal B", 2.75, 9, (8, 13)),
    ("Finca El Collado", 1.50, 5, (6, 10)),
    ("Parcela Umbría", 0.90, 4, (5, 8)),
    ("La Vegueta", 4.20, 12, (10, 16)),
    ("Monte Bajo", 1.20, 4, (6, 9)),
    ("Cerro Pelado", 2.00, 7, (7, 12)),
    ("Lindero Este", 1.65, 6, (6, 10)),
    ("Dehesa Alta", 2.95, 9, (8, 13)),
    ("Dehesa Baja", 1.70, 6, (7, 10)),
    ("Solana del Medio", 2.25, 7, (7, 11)),
    ("Valhondo", 3.60, 11, (9, 15)),
    ("La Noguera", 1.35, 5, (6, 9)),
    ("Barranco Frío", 2.55, 8, (8, 12)),
    ("El Chaparral", 4.05, 12, (10, 15)),
    ("Las Lomas", 1.95, 7, (7, 11)),
    ("Camino Viejo", 2.80, 9, (8, 13)),
    ("Fuente Seca", 1.55, 5, (6, 10)),
]

EXPENSE_CATEGORIES = [
    "Pozos",
    "Vallado",
    "Labrar",
    "Instalación riego",
    "Perros",
    "Plantel",
    "Riego",
    "Regadío Social",
    "Otros",
]

INCOME_CATEGORIES = [
    "Trufa negra extra",
    "Trufa negra primera",
    "Trufa negra segunda",
    "Trufa negra picada",
]


# Realistic truffle price evolution: early years lower, recent years higher
# Key: campaign start year → (price_min, price_max) in €/kg
def _price_range(cy: int) -> tuple[float, float]:
    if cy < 2018:
        return (120.0, 200.0)
    elif cy < 2021:
        return (180.0, 280.0)
    elif cy < 2023:
        return (250.0, 400.0)
    else:
        return (300.0, 600.0)


# Production ramp-up: plots need ~5 years to produce well
def _production_factor(plant_age_years: float) -> float:
    """0 → 0.0, 5 → 0.3, 8 → 0.75, 12+ → 1.0"""
    if plant_age_years < 4:
        return 0.0
    elif plant_age_years < 6:
        return 0.1 + (plant_age_years - 4) * 0.10
    elif plant_age_years < 9:
        return 0.3 + (plant_age_years - 6) * 0.15
    elif plant_age_years < 12:
        return 0.75 + (plant_age_years - 9) * 0.08
    return 1.0


@dataclass
class SeedSummary:
    plots: int = 0
    plants: int = 0
    expenses: int = 0
    incomes: int = 0
    wells: int = 0
    irrigation: int = 0
    truffle_events: int = 0
    plot_events: int = 0
    campaigns: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _random_date_in_campaign(
    rng: random.Random,
    cy: int,
    month_min: int = 5,
    month_max: int = 12,
) -> dt.date:
    """Random date within a campaign year, biased toward summer–autumn."""
    if month_max <= 12:
        year = cy
        month = rng.randint(month_min, month_max)
    else:
        # Spans into next year
        total_months = month_max - month_min + 1
        chosen = rng.randint(0, total_months - 1)
        abs_month = month_min + chosen
        if abs_month <= 12:
            year, month = cy, abs_month
        else:
            year, month = cy + 1, abs_month - 12
    day = rng.randint(1, 28)
    return dt.date(year, month, day)


def _harvest_date(rng: random.Random, cy: int) -> dt.date:
    """Truffle harvest season: November–February."""
    month = rng.randint(11, 14)  # 13=Jan+1, 14=Feb+1
    if month <= 12:
        return dt.date(cy, month, rng.randint(1, 28))
    else:
        return dt.date(cy + 1, month - 12, rng.randint(1, 28))


# ---------------------------------------------------------------------------
# Build objects
# ---------------------------------------------------------------------------


def _make_plants(
    rng: random.Random,
    user_id: int,
    plot_id: int,
    num_rows: int,
    cols_range: tuple[int, int],
) -> list[Plant]:
    plants = []
    for row_idx in range(num_rows):
        rl = row_label_from_index(row_idx)
        max_col = rng.randint(*cols_range)
        # Sparse: keep 75–100% of columns
        all_cols = list(range(1, max_col + 1))
        keep = max(1, int(len(all_cols) * rng.uniform(0.75, 1.0)))
        chosen = sorted(rng.sample(all_cols, k=keep))
        for vc in chosen:
            plants.append(
                Plant(
                    user_id=user_id,
                    plot_id=plot_id,
                    label=f"{rl}{vc}",
                    row_label=rl,
                    row_order=row_idx,
                    col_order=vc - 1,
                    visual_col=vc,
                )
            )
    return plants


def _make_expenses_for_plot(
    rng: random.Random,
    user_id: int,
    plot_id: int,
    planting_date: dt.date,
    campaign_years: list[int],
    has_irrigation: bool,
) -> list[Expense]:
    expenses = []
    first_cy = campaign_years[0]

    for cy in campaign_years:
        # Labrar: every year
        expenses.append(
            Expense(
                user_id=user_id,
                plot_id=plot_id,
                date=_random_date_in_campaign(rng, cy, 9, 11),
                description="Laboreo anual",
                person="Agustín Ruiz",
                amount=round(rng.uniform(180, 450), 2),
                category="Labrar",
            )
        )

        # Irrigation cost (if has irrigation)
        if has_irrigation:
            n_riego = rng.randint(2, 5)
            for _ in range(n_riego):
                expenses.append(
                    Expense(
                        user_id=user_id,
                        plot_id=plot_id,
                        date=_random_date_in_campaign(rng, cy, 6, 9),
                        description="Coste riego",
                        person="",
                        amount=round(rng.uniform(30, 120), 2),
                        category="Riego",
                    )
                )

        # Wells: first 3 years only
        age = cy - planting_date.year
        if age <= 3:
            expenses.append(
                Expense(
                    user_id=user_id,
                    plot_id=plot_id,
                    date=_random_date_in_campaign(rng, cy, 5, 8),
                    description="Pozos micorrización",
                    person="",
                    amount=round(rng.uniform(200, 600), 2),
                    category="Pozos",
                )
            )

        # Plantel: only in planting year
        if cy == first_cy and planting_date.year >= cy:
            expenses.append(
                Expense(
                    user_id=user_id,
                    plot_id=plot_id,
                    date=_random_date_in_campaign(rng, cy, 5, 7),
                    description="Adquisición plantel",
                    person="Vivero Sierra",
                    amount=round(rng.uniform(800, 3500), 2),
                    category="Plantel",
                )
            )

        # Perros: every 2–3 years
        if rng.random() < 0.4:
            expenses.append(
                Expense(
                    user_id=user_id,
                    plot_id=plot_id,
                    date=_random_date_in_campaign(rng, cy, 8, 11),
                    description="Adiestramiento perro trufero",
                    person="",
                    amount=round(rng.uniform(150, 400), 2),
                    category="Perros",
                )
            )

        # Otros: sporadic
        if rng.random() < 0.3:
            expenses.append(
                Expense(
                    user_id=user_id,
                    plot_id=plot_id,
                    date=_random_date_in_campaign(rng, cy, 5, 12),
                    description=rng.choice(
                        [
                            "Material mantenimiento",
                            "Transporte",
                            "Análisis suelo",
                            "Poda",
                            "Tratamiento fitosanitario",
                        ]
                    ),
                    person="",
                    amount=round(rng.uniform(50, 300), 2),
                    category="Otros",
                )
            )

    return expenses


def _make_general_expenses(
    rng: random.Random,
    user_id: int,
    campaign_years: list[int],
) -> list[Expense]:
    """Unassigned (general) expenses shared across all plots."""
    expenses = []
    for cy in campaign_years:
        # Regadío social: yearly
        expenses.append(
            Expense(
                user_id=user_id,
                plot_id=None,
                date=_random_date_in_campaign(rng, cy, 5, 7),
                description="Regadío social comunidad",
                person="Comunidad Regantes",
                amount=round(rng.uniform(200, 800), 2),
                category="Regadío Social",
            )
        )
        # Vallado: occasional
        if rng.random() < 0.25:
            expenses.append(
                Expense(
                    user_id=user_id,
                    plot_id=None,
                    date=_random_date_in_campaign(rng, cy, 5, 10),
                    description="Reparación/ampliación vallado",
                    person="",
                    amount=round(rng.uniform(300, 1500), 2),
                    category="Vallado",
                )
            )
        # Seguros / otros generales
        if rng.random() < 0.5:
            expenses.append(
                Expense(
                    user_id=user_id,
                    plot_id=None,
                    date=_random_date_in_campaign(rng, cy, 5, 11),
                    description=rng.choice(
                        ["Seguro explotación", "Asesoría", "Gasoil maquinaria"]
                    ),
                    person="",
                    amount=round(rng.uniform(100, 600), 2),
                    category="Otros",
                )
            )
    return expenses


def _make_incomes_for_plot(
    rng: random.Random,
    user_id: int,
    plot_id: int,
    planting_date: dt.date,
    num_plants: int,
    area_ha: float,
    campaign_years: list[int],
) -> list[Income]:
    incomes = []
    for cy in campaign_years:
        # Age at middle of campaign
        age = cy - planting_date.year + 0.5
        factor = _production_factor(age)
        if factor <= 0:
            continue

        # Base yield: 15–60 kg/ha at full production
        base_kg_ha = rng.uniform(15, 60)
        base_kg = base_kg_ha * area_ha * factor
        # Year-to-year variance ± 30%
        base_kg *= rng.uniform(0.7, 1.3)

        if base_kg < 0.3:
            continue

        # Split into 3–6 sales across Nov–Feb
        n_sales = rng.randint(3, 6)
        remainig_kg = base_kg
        pmin, pmax = _price_range(cy)

        for i in range(n_sales):
            if i == n_sales - 1:
                sale_kg = remainig_kg
            else:
                sale_kg = remainig_kg * rng.uniform(0.1, 0.5)
                remainig_kg -= sale_kg

            if sale_kg < 0.05:
                continue

            euros_per_kg = round(rng.uniform(pmin, pmax), 2)
            # Grade variation: extra costs more
            category = rng.choices(
                INCOME_CATEGORIES,
                weights=[20, 45, 25, 10],
            )[0]
            if "extra" in category:
                euros_per_kg = round(euros_per_kg * rng.uniform(1.1, 1.4), 2)
            elif "picada" in category:
                euros_per_kg = round(euros_per_kg * rng.uniform(0.3, 0.5), 2)

            incomes.append(
                Income(
                    user_id=user_id,
                    plot_id=plot_id,
                    date=_harvest_date(rng, cy),
                    amount_kg=round(sale_kg, 3),
                    euros_per_kg=euros_per_kg,
                    category=category,
                )
            )

    return incomes


def _make_wells_for_plot(
    rng: random.Random,
    user_id: int,
    plot_id: int,
    planting_date: dt.date,
    campaign_years: list[int],
) -> list[Well]:
    wells = []
    for cy in campaign_years:
        age = cy - planting_date.year
        if age < 0 or age > 4:
            continue
        # 1–3 well sessions per year while young
        n_sessions = rng.randint(1, 3)
        for _ in range(n_sessions):
            wells.append(
                Well(
                    user_id=user_id,
                    plot_id=plot_id,
                    date=_random_date_in_campaign(rng, cy, 5, 9),
                    wells_per_plant=rng.randint(1, 3),
                    expense_id=None,
                    notes=rng.choice(
                        ["", "Micorrización Tuber melanosporum", "Pozos nueva zona", ""]
                    ),
                )
            )
    return wells


def _make_irrigation_for_plot(
    rng: random.Random,
    user_id: int,
    plot_id: int,
    planting_date: dt.date,
    num_plants: int,
    area_ha: float,
    campaign_years: list[int],
) -> list[IrrigationRecord]:
    records = []
    for cy in campaign_years:
        age = cy - planting_date.year
        if age < 0:
            continue
        # Summer irrigation: June–September, 4–10 sessions
        n_sessions = rng.randint(4, 10)
        for _ in range(n_sessions):
            # ~20–80 l/plant per session
            litres_per_plant = rng.uniform(20, 80)
            water_m3 = round(litres_per_plant * num_plants / 1000, 2)
            records.append(
                IrrigationRecord(
                    user_id=user_id,
                    plot_id=plot_id,
                    date=_random_date_in_campaign(rng, cy, 6, 9),
                    water_m3=water_m3,
                    notes="",
                )
            )
    return records


def _make_plot_events_for_plot(
    rng: random.Random,
    user_id: int,
    plot_id: int,
    planting_date: dt.date,
    campaign_years: list[int],
) -> list[PlotEvent]:
    """
    Genera eventos de gestión agrícola (poda, labrado, picado) por campaña.

    Lógica realista:
    - Labrado (tilling): 1-2 veces al año, otoño (sep-nov)
    - Picado (digging): 1-2 veces al año, primavera (mar-may) y/o verano
    - Poda (pruning): cada 1-3 años, invierno (dic-feb) o primavera temprana
    """
    events: list[PlotEvent] = []
    for cy in campaign_years:
        age = cy - planting_date.year
        if age < 0:
            continue

        created_at = dt.datetime(
            cy,
            rng.randint(5, 12),
            rng.randint(1, 28),
            rng.randint(8, 18),
            rng.randint(0, 59),
            tzinfo=dt.timezone.utc,
        )

        # Labrado: casi todos los años
        n_tilling = rng.randint(1, 2)
        for _ in range(n_tilling):
            events.append(
                PlotEvent(
                    user_id=user_id,
                    plot_id=plot_id,
                    event_type=EventType.LABRADO.value,
                    date=_random_date_in_campaign(rng, cy, 9, 11),
                    notes=rng.choice(
                        ["", "Laboreo superficial", "Pase de cultivador", ""]
                    ),
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

        # Picado: la mayoría de años, principio de campaña
        if rng.random() < 0.80:
            n_digging = rng.randint(1, 2)
            for _ in range(n_digging):
                # Primavera (abr-jun) del año cy o inicio de temporada
                month = rng.randint(4, 6)
                events.append(
                    PlotEvent(
                        user_id=user_id,
                        plot_id=plot_id,
                        event_type=EventType.PICADO.value,
                        date=dt.date(cy, month, rng.randint(1, 28)),
                        notes=rng.choice(
                            ["", "Picado con motoazada", "Aireación suelo", ""]
                        ),
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )

        # Poda: cada 1-3 años, más frecuente en parcelas jóvenes
        prune_prob = 0.70 if age <= 5 else 0.40
        if rng.random() < prune_prob:
            # Invierno: dic del año anterior o ene-feb del año cy+1
            month = rng.choice([12, 1, 2])
            year = cy if month == 12 else cy + 1
            try:
                pdate = dt.date(year, month, rng.randint(1, 28))
            except ValueError:
                pdate = dt.date(year, month, 28)
            events.append(
                PlotEvent(
                    user_id=user_id,
                    plot_id=plot_id,
                    event_type=EventType.PODA.value,
                    date=pdate,
                    notes=rng.choice(["", "Poda formación", "Poda mantenimiento", ""]),
                    created_at=created_at,
                    updated_at=created_at,
                )
            )

    return events


def _timestamp_for_date(date_value: dt.date) -> dt.datetime:
    return dt.datetime.combine(
        date_value,
        dt.time(hour=12, minute=0, tzinfo=dt.timezone.utc),
    )


def _make_linked_plot_events_for_records(
    user_id: int,
    plot_id: int,
    irrigation_records: list[IrrigationRecord],
    well_records: list[Well],
) -> list[PlotEvent]:
    events: list[PlotEvent] = []

    for record in irrigation_records:
        timestamp = _timestamp_for_date(record.date)
        events.append(
            PlotEvent(
                user_id=user_id,
                plot_id=plot_id,
                event_type=EventType.RIEGO.value,
                date=record.date,
                notes=record.notes or "Riego generado desde seed",
                related_irrigation_id=record.id,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    for record in well_records:
        timestamp = _timestamp_for_date(record.date)
        events.append(
            PlotEvent(
                user_id=user_id,
                plot_id=plot_id,
                event_type=EventType.POZO.value,
                date=record.date,
                notes=record.notes or "Pozo generado desde seed",
                related_well_id=record.id,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )

    return events


def _make_truffle_events_for_plot(
    rng: random.Random,
    user_id: int,
    plot_id: int,
    plants: list[Plant],
    planting_date: dt.date,
    campaign_years: list[int],
) -> list[TruffleEvent]:
    if not plants:
        return []
    events = []
    for cy in campaign_years:
        age = cy - planting_date.year + 0.5
        factor = _production_factor(age)
        if factor <= 0:
            continue
        n_events = int(rng.randint(30, 180) * factor)
        for _ in range(n_events):
            plant = rng.choice(plants)
            created_at = dt.datetime(
                cy if rng.random() < 0.6 else cy + 1,
                rng.choice([11, 12, 1, 2]),
                rng.randint(1, 28),
                rng.randint(7, 18),
                rng.randint(0, 59),
                tzinfo=dt.timezone.utc,
            )
            undone_at = None
            if rng.random() < 0.08:
                undone_at = created_at + dt.timedelta(seconds=rng.randint(5, 120))
            events.append(
                TruffleEvent(
                    user_id=user_id,
                    plot_id=plot_id,
                    plant_id=plant.id,
                    source="qr" if rng.random() < 0.6 else "manual",
                    estimated_weight_grams=round(rng.uniform(5, 180), 1),
                    created_at=created_at,
                    undo_window_expires_at=created_at + dt.timedelta(seconds=30),
                    undone_at=undone_at,
                )
            )
    return events


# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------


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
        raise ValueError("No hay usuarios en la base de datos. Regístrate primero.")
    return user


async def seed(args: argparse.Namespace) -> SeedSummary:
    rng = random.Random(args.seed)
    summary = SeedSummary()

    # Campaign range ending at current campaign
    today = dt.date.today()
    current_cy = today.year if today.month >= 5 else today.year - 1
    start_cy = (
        args.start_campaign
        if args.start_campaign is not None
        else current_cy - max(args.years, 1) + 1
    )
    campaign_years = list(range(start_cy, current_cy + 1))
    summary.campaigns = campaign_years

    async with AsyncSessionLocal() as session:
        user = await _resolve_user(session, args.user_id)
        uid = user.id

        specs = PLOT_SPECS[: args.plots]

        for spec_name, area_ha, num_rows, cols_range in specs:
            # Planting date: stagger over the first 4 years of the range
            py = start_cy + rng.randint(0, min(3, len(campaign_years) - 1))
            planting_date = dt.date(py, rng.randint(1, 4), rng.randint(1, 28))
            production_start = dt.date(
                planting_date.year + rng.randint(5, 7),
                rng.randint(11, 12),
                rng.randint(1, 28),
            )
            has_irrigation = rng.random() < 0.85
            caudal_riego = round(rng.uniform(3.0, 20.0), 1) if has_irrigation else None

            plot = Plot(
                user_id=uid,
                name=spec_name,
                polygon=str(rng.randint(1, 30)),
                plot_num=str(rng.randint(100, 999)),
                cadastral_ref=f"CAT{rng.randint(10000, 99999)}",
                hydrant=f"H-{rng.randint(1, 20):02d}",
                sector=f"S{rng.randint(1, 4)}",
                num_plants=0,  # filled after flush
                planting_date=planting_date,
                area_ha=area_ha,
                production_start=production_start,
                percentage=0.0,
                has_irrigation=has_irrigation,
                caudal_riego=caudal_riego,
            )
            session.add(plot)
            await session.flush()

            # Plants
            plants = _make_plants(rng, uid, plot.id, num_rows, cols_range)
            session.add_all(plants)
            await session.flush()
            plot.num_plants = len(plants)
            summary.plants += len(plants)

            # Expenses (plot-assigned)
            exps = _make_expenses_for_plot(
                rng, uid, plot.id, planting_date, campaign_years, has_irrigation
            )
            session.add_all(exps)
            summary.expenses += len(exps)

            # Incomes
            incs = _make_incomes_for_plot(
                rng, uid, plot.id, planting_date, len(plants), area_ha, campaign_years
            )
            session.add_all(incs)
            summary.incomes += len(incs)

            # Wells
            ws = _make_wells_for_plot(rng, uid, plot.id, planting_date, campaign_years)
            session.add_all(ws)
            await session.flush()
            summary.wells += len(ws)

            # Irrigation
            irr: list[IrrigationRecord] = []
            if has_irrigation:
                irr = _make_irrigation_for_plot(
                    rng,
                    uid,
                    plot.id,
                    planting_date,
                    len(plants),
                    area_ha,
                    campaign_years,
                )
                session.add_all(irr)
                await session.flush()
                summary.irrigation += len(irr)

            # Truffle events
            evts = _make_truffle_events_for_plot(
                rng, uid, plot.id, plants, planting_date, campaign_years
            )
            session.add_all(evts)
            summary.truffle_events += len(evts)

            # Plot management events (poda, labrado, picado)
            pevts = _make_plot_events_for_plot(
                rng, uid, plot.id, planting_date, campaign_years
            )
            linked_pevts = _make_linked_plot_events_for_records(uid, plot.id, irr, ws)
            session.add_all(pevts + linked_pevts)
            summary.plot_events += len(pevts) + len(linked_pevts)

            summary.plots += 1

        # General (unassigned) expenses
        gen_exps = _make_general_expenses(rng, uid, campaign_years)
        session.add_all(gen_exps)
        summary.expenses += len(gen_exps)

        # Recalculate percentages for ALL user plots
        all_plots_res = await session.execute(select(Plot).where(Plot.user_id == uid))
        all_plots = all_plots_res.scalars().all()
        total_plants = sum(p.num_plants or 0 for p in all_plots)
        for p in all_plots:
            p.percentage = (
                ((p.num_plants or 0) / total_plants * 100.0) if total_plants else 0.0
            )

        await session.commit()

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    today = dt.date.today()
    default_start = (today.year if today.month >= 5 else today.year - 1) - 9

    p = argparse.ArgumentParser(
        description="Genera un dataset completo de demo para validar la aplicación."
    )
    p.add_argument(
        "--user-id",
        type=int,
        default=None,
        help="ID del usuario destino (por defecto: primer usuario)",
    )
    p.add_argument(
        "--plots",
        type=int,
        default=10,
        help=f"Número de parcelas (máx {len(PLOT_SPECS)}, default 10)",
    )
    p.add_argument(
        "--years",
        type=int,
        default=10,
        help="Número de campañas hasta la actual (default 10)",
    )
    p.add_argument(
        "--start-campaign",
        type=int,
        default=None,
        help=f"Campaña inicial (si no se indica, se calculan las últimas campañas; referencia actual: {default_start})",
    )
    p.add_argument(
        "--seed", type=int, default=42, help="Semilla aleatoria para reproducibilidad"
    )
    return p


async def _main_async(args: argparse.Namespace) -> None:
    args.plots = min(args.plots, len(PLOT_SPECS))
    summary = await seed(args)

    cy_labels = [campaign_label(cy) for cy in summary.campaigns]
    print("\n── Seed completado ─────────────────────────────────────")
    print(
        f"  Campañas:        {cy_labels[0]} → {cy_labels[-1]} ({len(cy_labels)} años)"
    )
    print(f"  Parcelas:        {summary.plots}")
    print(f"  Plantas:         {summary.plants}")
    print(f"  Gastos:          {summary.expenses}")
    print(f"  Ingresos:        {summary.incomes}")
    print(f"  Pozos:           {summary.wells}")
    print(f"  Riego:           {summary.irrigation}")
    print(f"  Eventos trufa:   {summary.truffle_events}")
    print(f"  Eventos parcela: {summary.plot_events}")
    print("─────────────────────────────────────────────────────────\n")


def main() -> None:
    args = _build_parser().parse_args()
    asyncio.run(_main_async(args))


if __name__ == "__main__":
    main()

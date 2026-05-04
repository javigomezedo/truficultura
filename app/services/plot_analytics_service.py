from __future__ import annotations

import datetime
from collections import defaultdict
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.rainfall import RainfallRecord
from app.models.well import Well
from app.schemas.plot_event import EventType
from app.services.rainfall_service import (
    resolve_municipio_cod,
    select_best_rainfall_per_day,
)
from app.utils import campaign_year


def _campaign_end_date(year: int) -> datetime.date:
    return datetime.date(year + 1, 4, 30)


def _safe_ratio(numerator: float, denominator: float) -> Optional[float]:
    if denominator <= 0:
        return None
    return numerator / denominator


def _days_since_last(
    last_date: Optional[datetime.date], campaign_year_value: int
) -> Optional[int]:
    if last_date is None:
        return None
    return (_campaign_end_date(campaign_year_value) - last_date).days


def _split_by_quantiles(rows: list[dict], metric_key: str) -> tuple[float, float]:
    sorted_rows = sorted(rows, key=lambda row: row[metric_key])
    n = len(sorted_rows)
    low_cut = sorted_rows[max(int(n * 0.33) - 1, 0)][metric_key]
    high_cut = sorted_rows[max(int(n * 0.66) - 1, 0)][metric_key]
    return low_cut, high_cut


def _water_band_summary(rows: list[dict]) -> list[dict]:
    if not rows:
        return []

    low_cut, high_cut = _split_by_quantiles(rows, "total_water_m3")
    bands = defaultdict(list)
    for row in rows:
        water = row["total_water_m3"]
        if water <= low_cut:
            band = "bajo"
        elif water <= high_cut:
            band = "medio"
        else:
            band = "alto"
        bands[band].append(row["total_production_kg"])

    band_ranges = {
        "bajo": {"min_m3": 0.0, "max_m3": low_cut},
        "medio": {"min_m3": low_cut, "max_m3": high_cut},
        "alto": {"min_m3": high_cut, "max_m3": None},
    }

    summary = []
    for key in ("bajo", "medio", "alto"):
        values = bands.get(key, [])
        summary.append(
            {
                "band": key,
                "count": len(values),
                "avg_production_kg": round(sum(values) / len(values), 3)
                if values
                else 0.0,
                "min_m3": band_ranges[key]["min_m3"],
                "max_m3": band_ranges[key]["max_m3"],
            }
        )
    return summary


def _build_plot_insights(dataset: list[dict]) -> dict:
    if not dataset:
        return {
            "status": "no_data",
            "messages": ["Sin campañas con datos para esta parcela."],
            "best_campaign_year": None,
            "best_campaign_production_kg": None,
        }

    best_row = max(dataset, key=lambda row: row["total_production_kg"])
    avg_production = sum(row["total_production_kg"] for row in dataset) / len(dataset)
    avg_water = sum(row["total_water_m3"] for row in dataset) / len(dataset)

    trend = "stable"
    if len(dataset) >= 2:
        first = dataset[0]["total_production_kg"]
        last = dataset[-1]["total_production_kg"]
        if last > first:
            trend = "up"
        elif last < first:
            trend = "down"

    messages = [
        f"Campaña con mayor producción: {best_row['campaign_year']} ({round(best_row['total_production_kg'], 3)} kg).",
        f"Producción media: {round(avg_production, 3)} kg por campaña.",
        f"Agua media (riego+lluvia): {round(avg_water, 3)} m3 por campaña.",
    ]

    if len(dataset) < 3:
        messages.append(
            "Muestra limitada: conviene al menos 3 campañas para conclusiones robustas."
        )

    return {
        "status": "ok",
        "messages": messages,
        "best_campaign_year": best_row["campaign_year"],
        "best_campaign_production_kg": round(best_row["total_production_kg"], 3),
        "average_production_kg": round(avg_production, 3),
        "average_water_m3": round(avg_water, 3),
        "trend": trend,
    }


async def get_plot_detail_context(
    db: AsyncSession,
    tenant_id: int,
    plot_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
) -> Optional[dict]:
    plot_result = await db.execute(
        select(Plot).where(Plot.id == plot_id, Plot.tenant_id == tenant_id)
    )
    plot = plot_result.scalar_one_or_none()
    if plot is None:
        return None

    dataset = await get_campaign_dataset(
        db,
        tenant_id,
        campaign_from=campaign_from,
        campaign_to=campaign_to,
        plot_ids=[plot_id],
    )

    labels = [row["campaign_year"] for row in dataset]
    production_series = [row["total_production_kg"] for row in dataset]
    water_series = [row["total_water_m3"] for row in dataset]
    pruning_series = [row["pruning_events_count"] for row in dataset]
    tilling_series = [row["tilling_events_count"] for row in dataset]
    scatter_points = [
        {
            "x": row["total_water_m3"],
            "y": row["total_production_kg"],
            "campaign_year": row["campaign_year"],
        }
        for row in dataset
        if row["total_water_m3"] > 0 and row["total_production_kg"] > 0
    ]

    insights = _build_plot_insights(dataset)

    return {
        "plot": plot,
        "dataset": dataset,
        "labels": labels,
        "production_series": production_series,
        "water_series": water_series,
        "pruning_series": pruning_series,
        "tilling_series": tilling_series,
        "scatter_points": scatter_points,
        "insights": insights,
    }


async def get_campaign_dataset(
    db: AsyncSession,
    tenant_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
    plot_ids: Optional[list[int]] = None,
) -> list[dict]:
    plots_stmt = select(Plot).where(Plot.tenant_id == tenant_id)
    if plot_ids:
        plots_stmt = plots_stmt.where(Plot.id.in_(plot_ids))
    plots_result = await db.execute(plots_stmt.order_by(Plot.name))
    plots = plots_result.scalars().all()

    if not plots:
        return []

    plot_map = {plot.id: plot for plot in plots}

    incomes_result = await db.execute(
        select(Income).where(
            Income.tenant_id == tenant_id, Income.plot_id.in_(plot_map.keys())
        )
    )
    incomes = incomes_result.scalars().all()

    irrigation_result = await db.execute(
        select(IrrigationRecord).where(
            IrrigationRecord.tenant_id == tenant_id,
            IrrigationRecord.plot_id.in_(plot_map.keys()),
        )
    )
    irrigation_records = irrigation_result.scalars().all()

    wells_result = await db.execute(
        select(Well).where(Well.tenant_id == tenant_id, Well.plot_id.in_(plot_map.keys()))
    )
    wells = wells_result.scalars().all()

    events_result = await db.execute(
        select(PlotEvent).where(
            PlotEvent.tenant_id == tenant_id,
            PlotEvent.plot_id.in_(plot_map.keys()),
        )
    )
    events = events_result.scalars().all()

    agg: dict[tuple[int, int], dict] = {}

    def get_row(plot_id: int, cy: int) -> dict:
        key = (plot_id, cy)
        if key not in agg:
            plot = plot_map[plot_id]
            agg[key] = {
                "tenant_id": tenant_id,
                "plot_id": plot_id,
                "plot_name": plot.name,
                "campaign_year": cy,
                "num_plants": plot.num_plants,
                "has_irrigation": plot.has_irrigation,
                "total_production_kg": 0.0,
                "production_kg_per_plant": None,
                "irrigation_m3": 0.0,
                "rain_m3": 0.0,
                "total_water_m3": 0.0,
                "total_water_liters": 0.0,
                "irrigation_events_count": 0,
                "water_m3_per_plant": None,
                "pruning_events_count": 0,
                "tilling_events_count": 0,
                "days_since_last_pruning": None,
                "days_since_last_tilling": None,
                "well_events_count": 0,
                "wells_per_plant_total": 0,
                "_last_pruning": None,
                "_last_tilling": None,
            }
        return agg[key]

    for income in incomes:
        if income.plot_id is None:
            continue
        cy = campaign_year(income.date)
        row = get_row(income.plot_id, cy)
        row["total_production_kg"] += income.amount_kg

    for item in irrigation_records:
        cy = campaign_year(item.date)
        row = get_row(item.plot_id, cy)
        row["irrigation_m3"] += item.water_m3
        row["irrigation_events_count"] += 1

    for item in wells:
        cy = campaign_year(item.date)
        row = get_row(item.plot_id, cy)
        row["well_events_count"] += 1
        row["wells_per_plant_total"] += item.wells_per_plant

    for event in events:
        cy = campaign_year(event.date)
        row = get_row(event.plot_id, cy)
        if event.event_type == EventType.PODA.value:
            row["pruning_events_count"] += 1
            row["_last_pruning"] = max(filter(None, [row["_last_pruning"], event.date]))
        elif event.event_type == EventType.LABRADO.value:
            row["tilling_events_count"] += 1
            row["_last_tilling"] = max(filter(None, [row["_last_tilling"], event.date]))

    rows = list(agg.values())

    for row in rows:
        row["total_production_kg"] = round(row["total_production_kg"], 3)
        row["irrigation_m3"] = round(row["irrigation_m3"], 3)
        row["rain_m3"] = round(row["rain_m3"], 3)
        row["total_water_m3"] = round(row["irrigation_m3"] + row["rain_m3"], 3)
        row["total_water_liters"] = round(row["total_water_m3"] * 1000, 1)

        row["production_kg_per_plant"] = _safe_ratio(
            row["total_production_kg"], float(row["num_plants"])
        )
        if row["production_kg_per_plant"] is not None:
            row["production_kg_per_plant"] = round(row["production_kg_per_plant"], 5)

        row["water_m3_per_plant"] = _safe_ratio(
            row["total_water_m3"], float(row["num_plants"])
        )
        if row["water_m3_per_plant"] is not None:
            row["water_m3_per_plant"] = round(row["water_m3_per_plant"], 5)

        row["days_since_last_pruning"] = _days_since_last(
            row["_last_pruning"], row["campaign_year"]
        )
        row["days_since_last_tilling"] = _days_since_last(
            row["_last_tilling"], row["campaign_year"]
        )

        row.pop("_last_pruning", None)
        row.pop("_last_tilling", None)

    # Acumular lluvia por (plot_id, campaign_year) con prioridad de fuente
    plot_municipio: dict[int, Optional[str]] = {
        p.id: resolve_municipio_cod(p) for p in plots
    }
    all_municipios = {m for m in plot_municipio.values() if m}
    plot_ids_list = list(plot_map.keys())

    if all_municipios:
        rain_stmt = select(RainfallRecord).where(
            RainfallRecord.tenant_id == tenant_id,
            or_(
                RainfallRecord.plot_id.in_(plot_ids_list),
                and_(
                    RainfallRecord.plot_id.is_(None),
                    RainfallRecord.municipio_cod.in_(list(all_municipios)),
                ),
            ),
        )
    else:
        rain_stmt = select(RainfallRecord).where(
            RainfallRecord.tenant_id == tenant_id,
            RainfallRecord.plot_id.in_(plot_ids_list),
        )

    all_rainfall = (await db.execute(rain_stmt)).scalars().all()

    for pid, municipio_cod in plot_municipio.items():
        daily_rain = select_best_rainfall_per_day(all_rainfall, pid, municipio_cod)
        plot = plot_map[pid]
        for date, (mm, _) in daily_rain.items():
            cy = campaign_year(date)
            row = get_row(pid, cy)
            if plot.area_ha is not None:
                row["rain_m3"] += mm * plot.area_ha * 10.0

    if campaign_from is not None:
        rows = [row for row in rows if row["campaign_year"] >= campaign_from]
    if campaign_to is not None:
        rows = [row for row in rows if row["campaign_year"] <= campaign_to]

    rows.sort(key=lambda item: (item["campaign_year"], item["plot_name"]))
    return rows


async def get_irrigation_vs_production_analysis(
    db: AsyncSession,
    tenant_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
    plot_ids: Optional[list[int]] = None,
) -> dict:
    rows = await get_campaign_dataset(
        db,
        tenant_id,
        campaign_from=campaign_from,
        campaign_to=campaign_to,
        plot_ids=plot_ids,
    )

    pairs = [
        row
        for row in rows
        if row["total_water_m3"] > 0 and row["total_production_kg"] > 0
    ]

    if not pairs:
        return {
            "sample_size": 0,
            "avg_water_m3": 0.0,
            "avg_production_kg": 0.0,
            "water_bands": [],
        }

    avg_water = sum(row["total_water_m3"] for row in pairs) / len(pairs)
    avg_production = sum(row["total_production_kg"] for row in pairs) / len(pairs)

    water_bands = _water_band_summary(pairs)

    return {
        "sample_size": len(pairs),
        "avg_water_m3": round(avg_water, 3),
        "avg_production_kg": round(avg_production, 3),
        "water_bands": water_bands,
    }


async def get_pruning_vs_production_analysis(
    db: AsyncSession,
    tenant_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
    plot_ids: Optional[list[int]] = None,
) -> dict:
    rows = await get_campaign_dataset(
        db,
        tenant_id,
        campaign_from=campaign_from,
        campaign_to=campaign_to,
        plot_ids=plot_ids,
    )
    pairs = [row for row in rows if row["total_production_kg"] > 0]

    with_pruning = [
        row["total_production_kg"] for row in pairs if row["pruning_events_count"] > 0
    ]
    without_pruning = [
        row["total_production_kg"] for row in pairs if row["pruning_events_count"] == 0
    ]

    avg_with = round(sum(with_pruning) / len(with_pruning), 3) if with_pruning else 0.0
    avg_without = (
        round(sum(without_pruning) / len(without_pruning), 3)
        if without_pruning
        else 0.0
    )

    delta = None
    if avg_without > 0:
        delta = round(((avg_with - avg_without) / avg_without) * 100, 3)

    return {
        "sample_size": len(pairs),
        "with_pruning_count": len(with_pruning),
        "without_pruning_count": len(without_pruning),
        "avg_production_with_pruning": avg_with,
        "avg_production_without_pruning": avg_without,
        "delta_percent": delta,
    }


async def get_tilling_vs_production_analysis(
    db: AsyncSession,
    tenant_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
    plot_ids: Optional[list[int]] = None,
) -> dict:
    rows = await get_campaign_dataset(
        db,
        tenant_id,
        campaign_from=campaign_from,
        campaign_to=campaign_to,
        plot_ids=plot_ids,
    )
    pairs = [row for row in rows if row["total_production_kg"] > 0]

    groups: dict[str, list[float]] = {
        "sin_labrado": [],
        "con_labrado": [],
    }
    for row in pairs:
        group_key = "con_labrado" if row["tilling_events_count"] > 0 else "sin_labrado"
        groups[group_key].append(row["total_production_kg"])

    summary = []
    for key in ("sin_labrado", "con_labrado"):
        values = groups[key]
        summary.append(
            {
                "group": key,
                "count": len(values),
                "avg_production_kg": round(sum(values) / len(values), 3)
                if values
                else 0.0,
            }
        )

    return {
        "sample_size": len(pairs),
        "groups": summary,
    }


def _detect_plateau_from_pairs(pairs: list[dict]) -> dict:
    """Detección de meseta en memoria sobre pares (water_m3 > 0, production_kg > 0)
    ya filtrados. Devuelve dict con status, plateau_start_m3 y marginal_gains.

    Marca la señal como 'inconclusive' si:
    - La meseta se detecta en la primera transición (señal demasiado corta / ruidosa).
    - Más del 60 % de las ganancias marginales son negativas (datos sin tendencia clara).
    En ambos casos se devuelve plateau_start_m3=None para no mostrar un umbral engañoso.
    """
    sorted_pairs = sorted(pairs, key=lambda row: row["total_water_m3"])
    marginal_gains: list[dict] = []
    plateau_start = None
    plateau_at_first = False
    negative_count = 0

    for i, (previous, current) in enumerate(zip(sorted_pairs, sorted_pairs[1:])):
        water_delta = current["total_water_m3"] - previous["total_water_m3"]
        production_delta = (
            current["total_production_kg"] - previous["total_production_kg"]
        )
        gain_per_m3 = None
        if water_delta > 0:
            gain_per_m3 = round(production_delta / water_delta, 5)
            if gain_per_m3 < 0:
                negative_count += 1
            if plateau_start is None and gain_per_m3 <= 0.02:
                plateau_start = current["total_water_m3"]
                if i == 0:
                    plateau_at_first = True

        marginal_gains.append(
            {
                "from_water_m3": previous["total_water_m3"],
                "to_water_m3": current["total_water_m3"],
                "water_delta": round(water_delta, 3),
                "production_delta": round(production_delta, 3),
                "gain_per_m3": gain_per_m3,
            }
        )

    valid_gains = [g for g in marginal_gains if g["gain_per_m3"] is not None]
    noisy = len(valid_gains) > 0 and (negative_count / len(valid_gains)) > 0.6
    inconclusive = plateau_at_first or noisy

    return {
        "status": "inconclusive" if inconclusive else "ok",
        "plateau_start_m3": None if inconclusive else plateau_start,
        "water_bands": _water_band_summary(pairs),
        "marginal_gains": marginal_gains,
    }


async def detect_irrigation_thresholds(
    db: AsyncSession,
    tenant_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
    plot_ids: Optional[list[int]] = None,
) -> dict:
    """Detecta el umbral de meseta de riego global.

    Estrategia B (preferida): si ≥2 parcelas individuales tienen umbral fiable,
    devuelve la mediana de sus mesetas (cada parcela se compara consigo misma
    a lo largo de las campañas, evitando mezclar diferencias entre bancales).

    Fallback A: si hay menos de 2 parcelas con umbral fiable, usa el dataset
    combinado (comportamiento original).
    """
    rows = await get_campaign_dataset(
        db,
        tenant_id,
        campaign_from=campaign_from,
        campaign_to=campaign_to,
        plot_ids=plot_ids,
    )
    pairs = [
        row
        for row in rows
        if row["total_water_m3"] > 0 and row["total_production_kg"] > 0
    ]
    if len(pairs) < 3:
        return {
            "sample_size": len(pairs),
            "status": "insufficient_data",
            "plateau_start_m3": None,
            "marginal_gains": [],
            "water_bands": [],
            "method": "insufficient_data",
            "contributing_plots": 0,
        }

    # --- Estrategia B: mediana de umbrales por parcela ---
    by_plot: dict[int, list[dict]] = {}
    for row in pairs:
        by_plot.setdefault(row["plot_id"], []).append(row)

    reliable_plateaus: list[float] = []
    for plot_rows in by_plot.values():
        if len(plot_rows) < 3:
            continue
        p = _detect_plateau_from_pairs(plot_rows)
        if p["status"] == "ok" and p["plateau_start_m3"] is not None:
            reliable_plateaus.append(p["plateau_start_m3"])

    if len(reliable_plateaus) >= 2:
        sorted_v = sorted(reliable_plateaus)
        n = len(sorted_v)
        median_val = (
            (sorted_v[n // 2 - 1] + sorted_v[n // 2]) / 2
            if n % 2 == 0
            else sorted_v[n // 2]
        )
        return {
            "sample_size": len(pairs),
            "status": "ok",
            "plateau_start_m3": round(median_val, 2),
            "marginal_gains": [],
            "water_bands": _water_band_summary(pairs),
            "method": "median_of_plots",
            "contributing_plots": len(reliable_plateaus),
        }

    # --- Fallback A: dataset combinado ---
    result = _detect_plateau_from_pairs(pairs)
    return {
        "sample_size": len(pairs),
        "method": "combined",
        "contributing_plots": 0,
        **result,
    }


async def get_all_plot_thresholds(
    db: AsyncSession,
    tenant_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
) -> list[dict]:
    """Devuelve el umbral de meseta de riego para cada parcela individualmente,
    calculado en memoria a partir de una sola llamada a get_campaign_dataset.
    Incluye tanto parcelas con datos suficientes como sin ellos.
    """
    rows = await get_campaign_dataset(
        db, tenant_id, campaign_from=campaign_from, campaign_to=campaign_to
    )
    by_plot: dict[int, list[dict]] = {}
    for row in rows:
        by_plot.setdefault(row["plot_id"], []).append(row)

    result: list[dict] = []
    for plot_id, plot_rows in by_plot.items():
        plot_name = plot_rows[0]["plot_name"]
        pairs = [
            r
            for r in plot_rows
            if r["total_water_m3"] > 0 and r["total_production_kg"] > 0
        ]
        if len(pairs) < 3:
            result.append(
                {
                    "plot_id": plot_id,
                    "plot_name": plot_name,
                    "sample_size": len(pairs),
                    "status": "insufficient_data",
                    "plateau_start_m3": None,
                }
            )
            continue

        plateau_data = _detect_plateau_from_pairs(pairs)
        result.append(
            {
                "plot_id": plot_id,
                "plot_name": plot_name,
                "sample_size": len(pairs),
                "status": plateau_data["status"],
                "plateau_start_m3": plateau_data["plateau_start_m3"],
            }
        )

    result.sort(key=lambda r: r["plot_name"])
    return result


async def get_multi_plot_comparison(
    db: AsyncSession,
    tenant_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
    plot_ids: Optional[list[int]] = None,
) -> dict:
    dataset = await get_campaign_dataset(
        db,
        tenant_id,
        campaign_from=campaign_from,
        campaign_to=campaign_to,
        plot_ids=plot_ids,
    )

    points = [
        {
            "x": row["total_water_m3"],
            "y": row["total_production_kg"],
            "plot_id": row["plot_id"],
            "plot_name": row["plot_name"],
            "campaign_year": row["campaign_year"],
            "kg_per_m3": round(row["total_production_kg"] / row["total_water_m3"], 5)
            if row["total_water_m3"] > 0
            else None,
        }
        for row in dataset
        if row["total_water_m3"] > 0 and row["total_production_kg"] > 0
    ]

    ranking_map: dict[int, dict] = {}
    for point in points:
        item = ranking_map.setdefault(
            point["plot_id"],
            {
                "plot_id": point["plot_id"],
                "plot_name": point["plot_name"],
                "sample_size": 0,
                "total_production_kg": 0.0,
                "total_water_m3": 0.0,
            },
        )
        item["sample_size"] += 1
        item["total_production_kg"] += point["y"]
        item["total_water_m3"] += point["x"]

    ranking = []
    for item in ranking_map.values():
        kg_per_m3 = None
        if item["total_water_m3"] > 0:
            kg_per_m3 = round(item["total_production_kg"] / item["total_water_m3"], 5)
        ranking.append(
            {
                **item,
                "total_production_kg": round(item["total_production_kg"], 3),
                "total_water_m3": round(item["total_water_m3"], 3),
                "kg_per_m3": kg_per_m3,
            }
        )

    ranking.sort(
        key=lambda row: (
            row["kg_per_m3"] is None,
            -(row["kg_per_m3"] or 0.0),
            row["plot_name"],
        )
    )

    return {
        "sample_size": len(points),
        "plots_included": len(ranking),
        "points": points,
        "efficiency_ranking": ranking,
    }


async def get_multi_plot_comparison(
    db: AsyncSession,
    tenant_id: int,
    *,
    campaign_from: Optional[int] = None,
    campaign_to: Optional[int] = None,
    plot_ids: Optional[list[int]] = None,
) -> dict:
    dataset = await get_campaign_dataset(
        db,
        tenant_id,
        campaign_from=campaign_from,
        campaign_to=campaign_to,
        plot_ids=plot_ids,
    )

    points = [
        {
            "x": row["total_water_m3"],
            "y": row["total_production_kg"],
            "plot_id": row["plot_id"],
            "plot_name": row["plot_name"],
            "campaign_year": row["campaign_year"],
            "kg_per_m3": round(row["total_production_kg"] / row["total_water_m3"], 5)
            if row["total_water_m3"] > 0
            else None,
        }
        for row in dataset
        if row["total_water_m3"] > 0 and row["total_production_kg"] > 0
    ]

    ranking_map: dict[int, dict] = {}
    for point in points:
        item = ranking_map.setdefault(
            point["plot_id"],
            {
                "plot_id": point["plot_id"],
                "plot_name": point["plot_name"],
                "sample_size": 0,
                "total_production_kg": 0.0,
                "total_water_m3": 0.0,
            },
        )
        item["sample_size"] += 1
        item["total_production_kg"] += point["y"]
        item["total_water_m3"] += point["x"]

    ranking = []
    for item in ranking_map.values():
        kg_per_m3 = None
        if item["total_water_m3"] > 0:
            kg_per_m3 = round(item["total_production_kg"] / item["total_water_m3"], 5)
        ranking.append(
            {
                **item,
                "total_production_kg": round(item["total_production_kg"], 3),
                "total_water_m3": round(item["total_water_m3"], 3),
                "kg_per_m3": kg_per_m3,
            }
        )

    ranking.sort(
        key=lambda row: (
            row["kg_per_m3"] is None,
            -(row["kg_per_m3"] or 0.0),
            row["plot_name"],
        )
    )

    return {
        "sample_size": len(points),
        "plots_included": len(ranking),
        "points": points,
        "efficiency_ranking": ranking,
    }

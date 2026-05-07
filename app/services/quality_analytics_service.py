"""Service: cross-reference harvest weight vs. sales by truffle quality."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.income import Income
from app.models.truffle_event import TruffleEvent
from app.models.truffle_quality import TruffleQuality
from app.utils import campaign_label, campaign_year

_QUALITIES = list(TruffleQuality)
_NO_QUALITY_LABEL = "Sin calidad"


def _quality_label(q: Optional[TruffleQuality]) -> str:
    if q is None:
        return _NO_QUALITY_LABEL
    return q.value.capitalize()


async def get_quality_analytics_context(
    db: AsyncSession,
    *,
    tenant_id: int,
    selected_campaign: Optional[int] = None,
) -> dict:
    """Return aggregated harvest and sales data by quality for the given tenant.

    Structure returned:
    {
        "campaigns": [2023, 2024, ...],                  # sorted desc
        "selected_campaign": 2024,                       # or None for all
        "qualities": ["Extra", "Primera", ...],          # including "Sin calidad"
        "harvest_kg": {"Extra": 12.3, ...},              # kg per quality
        "harvest_count": {"Extra": 42, ...},             # event count per quality
        "sales_kg": {"Extra": 10.0, ...},                # kg sold per quality
        "sales_eur": {"Extra": 850.0, ...},              # euros per quality
        "sales_eur_per_kg": {"Extra": 85.0, ...},        # avg €/kg per quality
    }
    """
    # Load truffle events
    stmt_events = select(TruffleEvent).where(
        TruffleEvent.tenant_id == tenant_id,
        TruffleEvent.undone_at.is_(None),
        TruffleEvent.estimated_weight_grams.isnot(None),
    )
    events_result = await db.execute(stmt_events)
    all_events = events_result.scalars().all()

    # Load incomes
    stmt_incomes = select(Income).where(Income.tenant_id == tenant_id)
    incomes_result = await db.execute(stmt_incomes)
    all_incomes = incomes_result.scalars().all()

    # Determine available campaigns from both sources
    campaigns: set[int] = set()
    for ev in all_events:
        if ev.created_at:
            campaigns.add(campaign_year(ev.created_at.date()))
    for inc in all_incomes:
        campaigns.add(campaign_year(inc.date))
    campaigns_sorted = sorted(campaigns, reverse=True)

    # Filter by campaign if selected
    if selected_campaign is not None:
        all_events = [
            ev
            for ev in all_events
            if ev.created_at
            and campaign_year(ev.created_at.date()) == selected_campaign
        ]
        all_incomes = [
            inc for inc in all_incomes if campaign_year(inc.date) == selected_campaign
        ]

    # Aggregate harvest by quality (grams → kg)
    harvest_grams: dict[str, float] = defaultdict(float)
    harvest_count: dict[str, int] = defaultdict(int)
    for ev in all_events:
        label = _quality_label(ev.quality)
        harvest_grams[label] += ev.estimated_weight_grams or 0.0
        harvest_count[label] += 1

    # Aggregate sales by quality
    sales_kg: dict[str, float] = defaultdict(float)
    sales_eur: dict[str, float] = defaultdict(float)
    for inc in all_incomes:
        label = _quality_label(inc.category)
        sales_kg[label] += inc.amount_kg or 0.0
        sales_eur[label] += (inc.amount_kg or 0.0) * (inc.euros_per_kg or 0.0)

    # Determine the ordered quality labels present in data
    all_labels: list[str] = []
    for q in _QUALITIES:
        lbl = q.value.capitalize()
        if harvest_grams.get(lbl, 0) > 0 or sales_kg.get(lbl, 0) > 0:
            all_labels.append(lbl)
    # Append "Sin calidad" at the end if any data exists under that bucket
    if (
        harvest_grams.get(_NO_QUALITY_LABEL, 0) > 0
        or sales_kg.get(_NO_QUALITY_LABEL, 0) > 0
    ):
        all_labels.append(_NO_QUALITY_LABEL)

    # If no data at all, use the full quality list for an empty chart
    if not all_labels:
        all_labels = [q.value.capitalize() for q in _QUALITIES]

    harvest_kg = {
        lbl: round(harvest_grams.get(lbl, 0.0) / 1000.0, 3) for lbl in all_labels
    }
    sales_kg_out = {lbl: round(sales_kg.get(lbl, 0.0), 3) for lbl in all_labels}
    sales_eur_out = {lbl: round(sales_eur.get(lbl, 0.0), 2) for lbl in all_labels}
    sales_eur_per_kg = {
        lbl: round(sales_eur_out[lbl] / sales_kg_out[lbl], 2)
        if sales_kg_out[lbl]
        else 0.0
        for lbl in all_labels
    }

    campaign_options = [
        {"year": y, "label": campaign_label(y)} for y in campaigns_sorted
    ]

    return {
        "campaigns": campaign_options,
        "selected_campaign": selected_campaign,
        "selected_campaign_label": campaign_label(selected_campaign)
        if selected_campaign
        else None,
        "qualities": all_labels,
        "harvest_kg": harvest_kg,
        "harvest_count": dict(harvest_count),
        "sales_kg": sales_kg_out,
        "sales_eur": sales_eur_out,
        "sales_eur_per_kg": sales_eur_per_kg,
    }

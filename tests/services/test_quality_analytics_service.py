from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.income import Income
from app.models.truffle_event import TruffleEvent
from app.models.truffle_quality import TruffleQuality
from app.services.quality_analytics_service import (
    _NO_QUALITY_LABEL,
    _quality_label,
    get_quality_analytics_context,
)
from tests.conftest import result


def _make_event(
    *,
    quality: TruffleQuality | None = TruffleQuality.EXTRA,
    weight_grams: float = 500.0,
    event_date: datetime.datetime | None = None,
) -> TruffleEvent:
    """Create a minimal TruffleEvent mock for testing."""
    if event_date is None:
        event_date = datetime.datetime(
            2025, 1, 15, 12, 0, 0, tzinfo=datetime.timezone.utc
        )
    ev = MagicMock(spec=TruffleEvent)
    ev.quality = quality
    ev.estimated_weight_grams = weight_grams
    ev.created_at = event_date
    ev.undone_at = None
    return ev


def _make_income(
    *,
    category: TruffleQuality | None = TruffleQuality.EXTRA,
    amount_kg: float = 2.0,
    euros_per_kg: float = 400.0,
    income_date: datetime.date | None = None,
) -> Income:
    """Create a minimal Income mock for testing."""
    if income_date is None:
        income_date = datetime.date(2025, 1, 20)
    inc = MagicMock(spec=Income)
    inc.category = category
    inc.amount_kg = amount_kg
    inc.euros_per_kg = euros_per_kg
    inc.date = income_date
    return inc


# ---------------------------------------------------------------------------
# _quality_label
# ---------------------------------------------------------------------------


def test_quality_label_none_returns_no_quality_label() -> None:
    assert _quality_label(None) == _NO_QUALITY_LABEL


def test_quality_label_returns_capitalized_value() -> None:
    assert _quality_label(TruffleQuality.EXTRA) == "Extra"
    assert _quality_label(TruffleQuality.PRIMERA) == "Primera"
    assert _quality_label(TruffleQuality.SEGUNDA) == "Segunda"


# ---------------------------------------------------------------------------
# get_quality_analytics_context — empty database
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_db_returns_default_quality_list() -> None:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([]), result([])])

    ctx = await get_quality_analytics_context(db, tenant_id=1)

    assert ctx["campaigns"] == []
    assert ctx["selected_campaign"] is None
    # All quality labels returned for an empty chart
    assert len(ctx["qualities"]) == len(TruffleQuality)
    assert ctx["harvest_kg"] == {q: 0.0 for q in ctx["qualities"]}


# ---------------------------------------------------------------------------
# get_quality_analytics_context — with data, no campaign filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_events_and_incomes_no_filter() -> None:
    event = _make_event(quality=TruffleQuality.EXTRA, weight_grams=1000.0)
    income = _make_income(
        category=TruffleQuality.EXTRA, amount_kg=0.5, euros_per_kg=500.0
    )

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([event]), result([income])])

    ctx = await get_quality_analytics_context(db, tenant_id=1)

    assert "Extra" in ctx["qualities"]
    assert ctx["harvest_kg"]["Extra"] == pytest.approx(1.0, abs=0.001)
    assert ctx["harvest_count"]["Extra"] == 1
    assert ctx["sales_kg"]["Extra"] == pytest.approx(0.5, abs=0.001)
    assert ctx["sales_eur"]["Extra"] == pytest.approx(250.0, abs=0.01)
    assert ctx["sales_eur_per_kg"]["Extra"] == pytest.approx(500.0, abs=0.01)


# ---------------------------------------------------------------------------
# get_quality_analytics_context — campaign filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_campaign_filter_limits_events_and_incomes() -> None:
    # Event in campaign 2024 (January 2025 is campaign_year 2024)
    event_in = _make_event(
        quality=TruffleQuality.PRIMERA,
        weight_grams=800.0,
        event_date=datetime.datetime(2025, 1, 10, 12, 0, tzinfo=datetime.timezone.utc),
    )
    # Event in campaign 2023 (January 2024 is campaign_year 2023)
    event_out = _make_event(
        quality=TruffleQuality.PRIMERA,
        weight_grams=500.0,
        event_date=datetime.datetime(2024, 1, 10, 12, 0, tzinfo=datetime.timezone.utc),
    )
    income_in = _make_income(
        category=TruffleQuality.PRIMERA,
        amount_kg=1.0,
        euros_per_kg=300.0,
        income_date=datetime.date(2025, 2, 1),  # campaign 2024
    )
    income_out = _make_income(
        category=TruffleQuality.PRIMERA,
        amount_kg=2.0,
        euros_per_kg=300.0,
        income_date=datetime.date(2024, 2, 1),  # campaign 2023
    )

    db = MagicMock()
    db.execute = AsyncMock(
        side_effect=[result([event_in, event_out]), result([income_in, income_out])]
    )

    ctx = await get_quality_analytics_context(db, tenant_id=1, selected_campaign=2024)

    assert ctx["selected_campaign"] == 2024
    # Only the in-campaign event and income should be counted
    assert ctx["harvest_kg"]["Primera"] == pytest.approx(0.8, abs=0.001)
    assert ctx["harvest_count"]["Primera"] == 1
    assert ctx["sales_kg"]["Primera"] == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# get_quality_analytics_context — "Sin calidad" bucket
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_quality_events_grouped_under_sin_calidad() -> None:
    event = _make_event(quality=None, weight_grams=300.0)
    income = _make_income(category=None, amount_kg=0.1, euros_per_kg=200.0)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([event]), result([income])])

    ctx = await get_quality_analytics_context(db, tenant_id=1)

    assert _NO_QUALITY_LABEL in ctx["qualities"]
    assert ctx["harvest_kg"][_NO_QUALITY_LABEL] == pytest.approx(0.3, abs=0.001)
    assert ctx["sales_kg"][_NO_QUALITY_LABEL] == pytest.approx(0.1, abs=0.001)


# ---------------------------------------------------------------------------
# get_quality_analytics_context — multiple campaigns detected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_campaigns_detected_from_events_and_incomes() -> None:
    event_2024 = _make_event(
        event_date=datetime.datetime(2025, 1, 10, 12, 0, tzinfo=datetime.timezone.utc)
    )
    income_2023 = _make_income(income_date=datetime.date(2024, 3, 1))

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([event_2024]), result([income_2023])])

    ctx = await get_quality_analytics_context(db, tenant_id=1)

    # Both campaign years should be detected (campaigns is a list of dicts)
    campaign_years = [c["year"] for c in ctx["campaigns"]]
    assert 2024 in campaign_years
    assert 2023 in campaign_years
    # Sorted descending
    assert campaign_years == sorted(campaign_years, reverse=True)


# ---------------------------------------------------------------------------
# get_quality_analytics_context — sales_eur_per_kg = 0 when no sales_kg
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sales_eur_per_kg_zero_when_no_sales() -> None:
    """Ensures no ZeroDivisionError when a quality has harvests but no sales."""
    event = _make_event(quality=TruffleQuality.SEGUNDA, weight_grams=600.0)

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result([event]), result([])])

    ctx = await get_quality_analytics_context(db, tenant_id=1)

    assert ctx["sales_eur_per_kg"]["Segunda"] == 0.0


# ---------------------------------------------------------------------------
# get_quality_analytics_context — multiple qualities in same tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_qualities_aggregated_correctly() -> None:
    events = [
        _make_event(quality=TruffleQuality.EXTRA, weight_grams=1000.0),
        _make_event(quality=TruffleQuality.EXTRA, weight_grams=500.0),
        _make_event(quality=TruffleQuality.PRIMERA, weight_grams=2000.0),
    ]
    incomes = [
        _make_income(category=TruffleQuality.EXTRA, amount_kg=1.0, euros_per_kg=600.0),
        _make_income(
            category=TruffleQuality.PRIMERA, amount_kg=1.5, euros_per_kg=400.0
        ),
    ]

    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result(events), result(incomes)])

    ctx = await get_quality_analytics_context(db, tenant_id=1)

    assert ctx["harvest_kg"]["Extra"] == pytest.approx(1.5, abs=0.001)
    assert ctx["harvest_count"]["Extra"] == 2
    assert ctx["harvest_kg"]["Primera"] == pytest.approx(2.0, abs=0.001)
    assert ctx["harvest_count"]["Primera"] == 1
    assert ctx["sales_eur"]["Extra"] == pytest.approx(600.0, abs=0.01)
    assert ctx["sales_eur_per_kg"]["Primera"] == pytest.approx(400.0, abs=0.01)

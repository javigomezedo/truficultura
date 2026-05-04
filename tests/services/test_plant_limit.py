"""Unit tests for plant limit logic in plots_service and import_service."""

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.conftest import result


# ── Helpers ────────────────────────────────────────────────────────────────────


def _make_plot(id: int = 1, num_plants: int = 0, tenant_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=id,
        tenant_id=tenant_id,
        num_plants=num_plants,
        name=f"Plot {id}",
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        planting_date=datetime.date(2020, 1, 1),
        area_ha=None,
        production_start=None,
        percentage=0.0,
        has_irrigation=False,
        recinto="1",
        caudal_riego=None,
        provincia_cod=None,
        municipio_cod=None,
        updated_by_user_id=None,
    )


def _db_with_execute_responses(*responses) -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(side_effect=list(responses))
    db.flush = AsyncMock()
    db.add = MagicMock()
    db.add_all = MagicMock()
    return db


# ── plots_service.create_plot — plant limit ────────────────────────────────────


@pytest.mark.asyncio
async def test_create_plot_no_limit_passes() -> None:
    """When plant_limit=None, no check is performed."""
    from app.services.plots_service import create_plot

    # _recalculate_percentages makes 1 db.execute call (list all plots)
    db = _db_with_execute_responses(
        result([]),  # _recalculate_percentages → list plots
    )
    db.add = MagicMock()

    await create_plot(
        db,
        tenant_id=1,
        name="Test",
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=600,
        planting_date=datetime.date(2020, 1, 1),
        area_ha=None,
        production_start=None,
        plant_limit=None,
    )
    # No exception raised


@pytest.mark.asyncio
async def test_create_plot_within_limit_passes() -> None:
    """300 existing + 100 new = 400 ≤ 500 — allowed."""
    from app.services.plots_service import create_plot

    # _get_effective_plant_total calls:
    #   1. plant_counts per plot (no rows → empty)
    #   2. plots list → one plot with num_plants=300
    # Then _recalculate_percentages:
    #   1. list all plots
    db = _db_with_execute_responses(
        result([]),  # plant_counts (no map)
        result([(1, 300)]),  # plots for effective total
        result([SimpleNamespace(id=1, num_plants=300)]),  # _recalculate_percentages
    )

    await create_plot(
        db,
        tenant_id=1,
        name="Test",
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=100,
        planting_date=datetime.date(2020, 1, 1),
        area_ha=None,
        production_start=None,
        plant_limit=500,
    )
    # No exception raised


@pytest.mark.asyncio
async def test_create_plot_exceeds_limit_raises() -> None:
    """450 existing + 100 new = 550 > 500 — raises PlantLimitExceededException."""
    from app.plan_access import PlantLimitExceededException
    from app.services.plots_service import create_plot

    db = _db_with_execute_responses(
        result([]),  # plant_counts (no map)
        result([(1, 450)]),  # plots for effective total
    )

    with pytest.raises(PlantLimitExceededException) as exc_info:
        await create_plot(
            db,
            tenant_id=1,
            name="Test",
            polygon="",
            plot_num="",
            cadastral_ref="",
            hydrant="",
            sector="",
            num_plants=100,
            planting_date=datetime.date(2020, 1, 1),
            area_ha=None,
            production_start=None,
            plant_limit=500,
        )
    assert exc_info.value.limit == 500


@pytest.mark.asyncio
async def test_create_plot_zero_plants_skips_limit_check() -> None:
    """num_plants=0 → limit check is skipped entirely."""
    from app.services.plots_service import create_plot

    # Only _recalculate_percentages executes (no effective_total query)
    db = _db_with_execute_responses(
        result([]),  # _recalculate_percentages
    )

    await create_plot(
        db,
        tenant_id=1,
        name="Test",
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=0,
        planting_date=datetime.date(2020, 1, 1),
        area_ha=None,
        production_start=None,
        plant_limit=500,
    )
    # No exception raised


# ── plots_service.update_plot — plant limit ────────────────────────────────────


@pytest.mark.asyncio
async def test_update_plot_not_increasing_skips_check() -> None:
    """Decreasing num_plants — no limit check."""
    from app.services.plots_service import update_plot

    plot = _make_plot(id=1, num_plants=200, tenant_id=1)
    # Only _recalculate_percentages executes
    db = _db_with_execute_responses(
        result([plot]),  # _recalculate_percentages list
    )

    await update_plot(
        db,
        plot,
        name="X",
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=100,  # decreasing — no check
        planting_date=datetime.date(2020, 1, 1),
        area_ha=None,
        production_start=None,
        plant_limit=500,
    )


@pytest.mark.asyncio
async def test_update_plot_num_plants_not_increased_skips_check() -> None:
    """When new num_plants == old num_plants, no limit check DB queries are made."""
    from app.services.plots_service import update_plot

    plot = _make_plot(id=1, num_plants=600, tenant_id=1)
    db = _db_with_execute_responses(
        result([plot]),  # _recalculate_percentages
    )

    # Same value as old → condition `num_plants > old` is False → no limit query
    await update_plot(
        db,
        plot,
        name="X",
        polygon="",
        plot_num="",
        cadastral_ref="",
        hydrant="",
        sector="",
        num_plants=600,
        planting_date=datetime.date(2020, 1, 1),
        area_ha=None,
        production_start=None,
        plant_limit=500,
    )


@pytest.mark.asyncio
async def test_update_plot_exceeds_limit_raises() -> None:
    """other_total=450, new num_plants=100, limit=500 → 550 > 500 raises."""
    from app.plan_access import PlantLimitExceededException
    from app.services.plots_service import update_plot

    plot = _make_plot(id=1, num_plants=50, tenant_id=1)
    db = _db_with_execute_responses(
        result([]),  # plant_counts for effective_total (no Plant rows)
        result([(2, 450)]),  # other plots (plot 2 has 450 num_plants)
    )

    with pytest.raises(PlantLimitExceededException) as exc_info:
        await update_plot(
            db,
            plot,
            name="X",
            polygon="",
            plot_num="",
            cadastral_ref="",
            hydrant="",
            sector="",
            num_plants=100,
            planting_date=datetime.date(2020, 1, 1),
            area_ha=None,
            production_start=None,
            plant_limit=500,
        )
    assert exc_info.value.limit == 500


# ── import_service.import_plots_csv — plant limit ─────────────────────────────


@pytest.mark.asyncio
async def test_import_plots_csv_no_limit_passes() -> None:
    """plant_limit=None → no check, import proceeds normally."""
    from app.services.import_service import import_plots_csv

    csv_content = b"Parcela A;15/03/2020;;;;;;200\n"

    with patch("app.services.plots_service._recalculate_percentages", new=AsyncMock()):
        db = MagicMock()
        db.add_all = MagicMock()
        db.flush = AsyncMock()
        db.execute = AsyncMock()

        rows, warnings = await import_plots_csv(
            db, csv_content, tenant_id=1, plant_limit=None
        )
    assert len(warnings) == 0


@pytest.mark.asyncio
async def test_import_plots_csv_exceeds_limit_raises() -> None:
    """300 existing + 300 new = 600 > 500 → raises PlantLimitExceededException."""
    from app.plan_access import PlantLimitExceededException
    from app.services.import_service import import_plots_csv

    # CSV: two plots with 150 plants each = 300 new
    csv_content = b"Parcela A;15/03/2020;;;;;;150\nParcela B;15/03/2020;;;;;;150\n"

    with patch(
        "app.services.plots_service._get_effective_plant_total",
        new=AsyncMock(return_value=300),
    ):
        db = MagicMock()
        db.add_all = MagicMock()
        db.flush = AsyncMock()

        with pytest.raises(PlantLimitExceededException) as exc_info:
            await import_plots_csv(db, csv_content, tenant_id=1, plant_limit=500)

    assert exc_info.value.limit == 500


@pytest.mark.asyncio
async def test_import_plots_csv_within_limit_passes() -> None:
    """100 existing + 200 new = 300 ≤ 500 → no exception."""
    from app.services.import_service import import_plots_csv

    csv_content = b"Parcela A;15/03/2020;;;;;;200\n"

    with (
        patch(
            "app.services.plots_service._get_effective_plant_total",
            new=AsyncMock(return_value=100),
        ),
        patch("app.services.plots_service._recalculate_percentages", new=AsyncMock()),
    ):
        db = MagicMock()
        db.add_all = MagicMock()
        db.flush = AsyncMock()

        rows, warnings = await import_plots_csv(
            db, csv_content, tenant_id=1, plant_limit=500
        )

    assert len(rows) == 1

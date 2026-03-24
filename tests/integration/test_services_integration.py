from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Expense, Income, Plot  # noqa: F401 - ensure metadata is loaded
from app.services.dashboard_service import build_dashboard_context
from app.services.expenses_service import create_expense, get_expenses_list_context
from app.services.charts_service import build_charts_context
from app.services.incomes_service import create_income, get_incomes_list_context
from app.services.plots_service import create_plot, delete_plot, get_plot
from app.services.reports_service import build_profitability_context


async def _build_sessionmaker(db_file: Path) -> tuple:
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_maker


@pytest.mark.asyncio
async def test_services_crud_flow_with_real_db(tmp_path: Path) -> None:
    engine, session_maker = await _build_sessionmaker(tmp_path / "crud.sqlite3")

    try:
        async with session_maker() as db:
            plot = await create_plot(
                db,
                name="Bancal Test",
                polygon="1",
                cadastral_ref="10",
                hydrant="H1",
                sector="S1",
                num_holm_oaks=50,
                planting_date=datetime.date(2021, 1, 1),
                area_ha=2.0,
                production_start=datetime.date(2024, 1, 1),
                percentage=100.0,
                user_id=1,
            )
            await db.commit()

            fetched = await get_plot(db, plot.id, user_id=1)
            assert fetched is not None
            assert fetched.name == "Bancal Test"

            await create_expense(
                db,
                date=datetime.date(2025, 5, 10),
                description="Riego",
                person="Javi",
                plot_id=plot.id,
                amount=25.0,
                user_id=1,
            )
            await create_income(
                db,
                date=datetime.date(2025, 12, 10),
                plot_id=plot.id,
                amount_kg=2.0,
                category="A",
                euros_per_kg=50.0,
                user_id=1,
            )
            await db.commit()

            expenses_ctx = await get_expenses_list_context(db, 2025, user_id=1)
            incomes_ctx = await get_incomes_list_context(db, 2025, user_id=1)

            assert len(expenses_ctx["expenses"]) == 1
            assert expenses_ctx["total"] == 25.0
            assert len(incomes_ctx["incomes"]) == 1
            assert incomes_ctx["total_euros"] == 100.0

            await delete_plot(db, plot)
            await db.commit()

            assert await get_plot(db, plot.id, user_id=1) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_and_reports_context_with_real_db(tmp_path: Path) -> None:
    engine, session_maker = await _build_sessionmaker(tmp_path / "reportes.sqlite3")

    try:
        async with session_maker() as db:
            p1 = await create_plot(
                db,
                name="P1",
                polygon="1",
                cadastral_ref="1",
                hydrant="H1",
                sector="S1",
                num_holm_oaks=10,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=datetime.date(2023, 1, 1),
                percentage=60.0,
                user_id=1,
            )
            p2 = await create_plot(
                db,
                name="P2",
                polygon="2",
                cadastral_ref="2",
                hydrant="H2",
                sector="S2",
                num_holm_oaks=10,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=datetime.date(2023, 1, 1),
                percentage=40.0,
                user_id=1,
            )

            await create_expense(
                db,
                date=datetime.date(2025, 5, 1),
                description="Asignado",
                person="A",
                plot_id=p1.id,
                amount=100.0,
                user_id=1,
            )
            await create_expense(
                db,
                date=datetime.date(2025, 5, 2),
                description="No asignado",
                person="A",
                plot_id=None,
                amount=50.0,
                user_id=1,
            )

            await create_income(
                db,
                date=datetime.date(2025, 12, 1),
                plot_id=p1.id,
                amount_kg=1.0,
                category="A",
                euros_per_kg=40.0,
                user_id=1,
            )
            await create_income(
                db,
                date=datetime.date(2025, 12, 2),
                plot_id=p2.id,
                amount_kg=1.0,
                category="A",
                euros_per_kg=30.0,
                user_id=1,
            )
            await db.commit()

            dashboard_ctx = await build_dashboard_context(db, user_id=1)
            report_ctx = await build_profitability_context(db, user_id=1)

            assert dashboard_ctx["grand_expenses"] == 150.0
            assert dashboard_ctx["grand_incomes"] == 70.0
            assert dashboard_ctx["grand_profitability"] == -80.0
            assert len(dashboard_ctx["campaign_rows"]) == 1

            assert report_ctx["grand_total_incomes"] == 70.0
            assert report_ctx["grand_total_expenses"] == 150.0
            assert report_ctx["grand_total_profitability"] == -80.0
            assert report_ctx["all_years"] == [2025]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_charts_context_with_real_db(tmp_path: Path) -> None:
    engine, session_maker = await _build_sessionmaker(tmp_path / "graficas.sqlite3")

    try:
        async with session_maker() as db:
            plot = await create_plot(
                db,
                name="PG",
                polygon="1",
                cadastral_ref="1",
                hydrant="H",
                sector="S",
                num_holm_oaks=10,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=2.0,
                production_start=datetime.date(2023, 1, 1),
                percentage=100.0,
                user_id=1,
            )
            await create_expense(
                db,
                date=datetime.date(2025, 11, 30),
                description="G",
                person="X",
                plot_id=plot.id,
                amount=10.0,
                user_id=1,
            )
            await create_income(
                db,
                date=datetime.date(2025, 12, 1),
                plot_id=plot.id,
                amount_kg=4.0,
                category="A",
                euros_per_kg=20.0,
                user_id=1,
            )
            await db.commit()

            ctx = await build_charts_context(
                db, campaign=2025, plot_id=plot.id, user_id=1
            )

            assert ctx["selected_campaign"] == 2025
            assert ctx["selected_plot_id"] == plot.id
            assert json.loads(ctx["week_labels"]) != []
            assert json.loads(ctx["income_values"]) == [80.0]
            assert json.loads(ctx["expense_values"]) == [10.0]
            assert len(ctx["kg_ha_table"]) == 1
    finally:
        await engine.dispose()

from __future__ import annotations

import datetime
import json
from pathlib import Path
from datetime import timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Expense, Income, IrrigationRecord, Plant, Plot, User, Well  # noqa: F401 - ensure metadata is loaded
from app.services.dashboard_service import build_dashboard_context
from app.services.expenses_service import create_expense, get_expenses_list_context
from app.services.charts_service import build_charts_context
from app.services.incomes_service import create_income, get_incomes_list_context
from app.services.irrigation_service import (
    get_irrigation_record,
    list_irrigation_records,
)
from app.services.plots_service import create_plot, delete_plot, get_plot
from app.services.plants_service import get_plant, list_plants
from app.services.reports_service import build_profitability_context
from app.services.truffle_events_service import (
    create_event,
    get_counts_by_plant,
    list_events,
)
from app.services.wells_service import get_well, list_wells


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
                tenant_id=1,
                name="Bancal Test",
                polygon="1",
                plot_num="10",
                cadastral_ref="44223A021001200000FP",
                hydrant="H1",
                sector="S1",
                num_plants=50,
                planting_date=datetime.date(2021, 1, 1),
                area_ha=2.0,
                production_start=datetime.date(2024, 1, 1),
            )
            await db.commit()

            fetched = await get_plot(db, plot.id, tenant_id=1)
            assert fetched is not None
            assert fetched.name == "Bancal Test"

            await create_expense(
                db,
                date=datetime.date(2025, 5, 10),
                description="Riego",
                person="Javi",
                plot_id=plot.id,
                amount=25.0,
                tenant_id=1,
            )
            await create_income(
                db,
                date=datetime.date(2025, 12, 10),
                plot_id=plot.id,
                amount_kg=2.0,
                category="A",
                euros_per_kg=50.0,
                tenant_id=1,
            )
            await db.commit()

            expenses_ctx = await get_expenses_list_context(db, 2025, tenant_id=1)
            incomes_ctx = await get_incomes_list_context(db, 2025, tenant_id=1)

            assert len(expenses_ctx["expenses"]) == 1
            assert expenses_ctx["total"] == 25.0
            assert len(incomes_ctx["incomes"]) == 1
            assert incomes_ctx["total_euros"] == 100.0

            await delete_plot(db, plot)
            await db.commit()

            assert await get_plot(db, plot.id, tenant_id=1) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_and_reports_context_with_real_db(tmp_path: Path) -> None:
    engine, session_maker = await _build_sessionmaker(tmp_path / "reportes.sqlite3")

    try:
        async with session_maker() as db:
            p1 = await create_plot(
                db,
                tenant_id=1,
                name="P1",
                polygon="1",
                plot_num="1",
                cadastral_ref="44223A021001200000FP",
                hydrant="H1",
                sector="S1",
                num_plants=10,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=datetime.date(2023, 1, 1),
            )
            p2 = await create_plot(
                db,
                tenant_id=1,
                name="P2",
                polygon="2",
                plot_num="2",
                cadastral_ref="44223A021001200000GP",
                hydrant="H2",
                sector="S2",
                num_plants=10,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=datetime.date(2023, 1, 1),
            )

            await create_expense(
                db,
                date=datetime.date(2025, 5, 1),
                description="Asignado",
                person="A",
                plot_id=p1.id,
                amount=100.0,
                tenant_id=1,
            )
            await create_expense(
                db,
                date=datetime.date(2025, 5, 2),
                description="No asignado",
                person="A",
                plot_id=None,
                amount=50.0,
                tenant_id=1,
            )

            await create_income(
                db,
                date=datetime.date(2025, 12, 1),
                plot_id=p1.id,
                amount_kg=1.0,
                category="A",
                euros_per_kg=40.0,
                tenant_id=1,
            )
            await create_income(
                db,
                date=datetime.date(2025, 12, 2),
                plot_id=p2.id,
                amount_kg=1.0,
                category="A",
                euros_per_kg=30.0,
                tenant_id=1,
            )
            await db.commit()

            dashboard_ctx = await build_dashboard_context(db, tenant_id=1)
            report_ctx = await build_profitability_context(db, tenant_id=1)

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
                tenant_id=1,
                name="PG",
                polygon="1",
                plot_num="1",
                cadastral_ref="44223A021001200000FP",
                hydrant="H",
                sector="S",
                num_plants=10,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=2.0,
                production_start=datetime.date(2023, 1, 1),
            )
            await create_expense(
                db,
                date=datetime.date(2025, 11, 30),
                description="G",
                person="X",
                plot_id=plot.id,
                amount=10.0,
                tenant_id=1,
            )
            await create_income(
                db,
                date=datetime.date(2025, 12, 1),
                plot_id=plot.id,
                amount_kg=4.0,
                category="A",
                euros_per_kg=20.0,
                tenant_id=1,
            )
            await db.commit()

            ctx = await build_charts_context(
                db, campaign=2025, plot_id=plot.id, tenant_id=1
            )

            assert ctx["selected_campaign"] == 2025
            assert ctx["selected_plot_id"] == plot.id
            assert json.loads(ctx["week_labels"]) != []
            assert json.loads(ctx["income_values"]) == [80.0]
            assert json.loads(ctx["expense_values"]) == [10.0]
            assert len(ctx["kg_ha_table"]) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_truffle_events_campaign_and_undo_filters_with_real_db(
    tmp_path: Path,
) -> None:
    engine, session_maker = await _build_sessionmaker(tmp_path / "trufas.sqlite3")

    try:
        async with session_maker() as db:
            user = User(
                username="javier",
                hashed_password="hash",
                first_name="Javier",
                last_name="Gomez",
                email="javier@example.com",
                role="user",
                is_active=True,
            )
            db.add(user)
            await db.flush()

            plot = await create_plot(
                db,
                tenant_id=user.id,
                name="Parcela Trufas",
                polygon="1",
                plot_num="10",
                cadastral_ref="44223A021001200000FP",
                hydrant="H1",
                sector="S1",
                num_plants=2,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=datetime.date(2023, 1, 1),
            )

            p1 = Plant(
                plot_id=plot.id,
                tenant_id=user.id,
                label="A1",
                row_label="A",
                row_order=0,
                col_order=0,
            )
            p2 = Plant(
                plot_id=plot.id,
                tenant_id=user.id,
                label="A2",
                row_label="A",
                row_order=0,
                col_order=1,
            )
            db.add(p1)
            db.add(p2)
            await db.flush()

            # Campaign 2025 active event
            e1 = await create_event(
                db,
                plant_id=p1.id,
                plot_id=plot.id,
                tenant_id=user.id,
                source="manual",
                dedupe_window_seconds=0,
            )
            e1.created_at = datetime.datetime(2025, 5, 2, 10, 0, 0, tzinfo=timezone.utc)
            e1.undo_window_expires_at = e1.created_at + datetime.timedelta(seconds=30)

            # Campaign 2025 then undone
            e2 = await create_event(
                db,
                plant_id=p1.id,
                plot_id=plot.id,
                tenant_id=user.id,
                source="qr",
                dedupe_window_seconds=0,
            )
            e2.created_at = datetime.datetime(2025, 6, 1, 11, 0, 0, tzinfo=timezone.utc)
            e2.undo_window_expires_at = e2.created_at + datetime.timedelta(seconds=30)
            e2.undone_at = datetime.datetime(2025, 6, 1, 11, 0, 10, tzinfo=timezone.utc)

            # Campaign 2024 active event
            e3 = await create_event(
                db,
                plant_id=p2.id,
                plot_id=plot.id,
                tenant_id=user.id,
                source="manual",
                dedupe_window_seconds=0,
            )
            e3.created_at = datetime.datetime(
                2024, 12, 15, 8, 0, 0, tzinfo=timezone.utc
            )
            e3.undo_window_expires_at = e3.created_at + datetime.timedelta(seconds=30)

            await db.commit()

            counts_2025 = await get_counts_by_plant(
                db,
                plot_id=plot.id,
                tenant_id=user.id,
                campaign_year=2025,
            )
            # e1 counts, e2 does not (undone)
            assert counts_2025 == {p1.id: 1}

            events_all = await list_events(
                db,
                tenant_id=user.id,
                campaign_year=2025,
                include_undone=True,
            )
            assert len(events_all) == 2

            events_active = await list_events(
                db,
                tenant_id=user.id,
                campaign_year=2025,
                include_undone=False,
            )
            assert len(events_active) == 1
            assert events_active[0].id == e1.id
    finally:
        await engine.dispose()


# ---------------------------------------------------------------------------
# Auditoría de seguridad: aislamiento cross-tenant
# Garantizan que los datos del Usuario B no son accesibles por el Usuario A
# ---------------------------------------------------------------------------


async def _create_user(db, username: str, email: str) -> User:
    user = User(
        username=username,
        hashed_password="hash",
        first_name="Test",
        last_name="User",
        email=email,
        role="user",
        is_active=True,
        email_confirmed=True,
    )
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_cross_tenant_plots_isolation(tmp_path: Path) -> None:
    """Usuario A no puede leer la parcela del Usuario B por su ID."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "ct_plots.sqlite3")
    try:
        async with session_maker() as db:
            user_a = await _create_user(db, "user_a", "a@example.com")
            user_b = await _create_user(db, "user_b", "b@example.com")

            plot_b = await create_plot(
                db,
                tenant_id=user_b.id,
                name="Parcela de B",
                polygon="1",
                plot_num="1",
                cadastral_ref="REF001",
                hydrant="H1",
                sector="S1",
                num_plants=10,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=None,
            )
            await db.commit()

            # A pide la parcela de B por su id → debe retornar None
            result = await get_plot(db, plot_b.id, tenant_id=user_a.id)
            assert result is None

            # A pide sus propias parcelas → lista vacía (no incluye parcela de B)
            from app.services.plots_service import list_plots

            plots_a = await list_plots(db, tenant_id=user_a.id)
            assert all(p.tenant_id == user_a.id for p in plots_a)
            assert plot_b.id not in {p.id for p in plots_a}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_expenses_isolation(tmp_path: Path) -> None:
    """El listado de gastos del Usuario A no incluye gastos del Usuario B."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "ct_expenses.sqlite3")
    try:
        async with session_maker() as db:
            user_a = await _create_user(db, "user_a", "a@example.com")
            user_b = await _create_user(db, "user_b", "b@example.com")

            await create_expense(
                db,
                date=datetime.date(2025, 6, 1),
                description="Gasto secreto de B",
                person="B",
                plot_id=None,
                amount=999.0,
                tenant_id=user_b.id,
            )
            await db.commit()

            ctx_a = await get_expenses_list_context(db, 2025, tenant_id=user_a.id)
            assert len(ctx_a["expenses"]) == 0
            assert ctx_a["total"] == 0.0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_incomes_isolation(tmp_path: Path) -> None:
    """El listado de ingresos del Usuario A no incluye ingresos del Usuario B."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "ct_incomes.sqlite3")
    try:
        async with session_maker() as db:
            user_a = await _create_user(db, "user_a", "a@example.com")
            user_b = await _create_user(db, "user_b", "b@example.com")

            await create_income(
                db,
                date=datetime.date(2025, 11, 1),
                plot_id=None,
                amount_kg=50.0,
                category="A",
                euros_per_kg=100.0,
                tenant_id=user_b.id,
            )
            await db.commit()

            ctx_a = await get_incomes_list_context(db, 2025, tenant_id=user_a.id)
            assert len(ctx_a["incomes"]) == 0
            assert ctx_a["total_euros"] == 0.0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_plants_isolation(tmp_path: Path) -> None:
    """Las plantas del Usuario B no aparecen al consultar las del Usuario A."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "ct_plants.sqlite3")
    try:
        async with session_maker() as db:
            user_a = await _create_user(db, "user_a", "a@example.com")
            user_b = await _create_user(db, "user_b", "b@example.com")

            plot_a = await create_plot(
                db,
                tenant_id=user_a.id,
                name="P-A",
                polygon="1",
                plot_num="1",
                cadastral_ref="REF001",
                hydrant="H1",
                sector="S1",
                num_plants=5,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=None,
            )
            plot_b = await create_plot(
                db,
                tenant_id=user_b.id,
                name="P-B",
                polygon="2",
                plot_num="2",
                cadastral_ref="REF002",
                hydrant="H2",
                sector="S2",
                num_plants=5,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=None,
            )

            plant_b = Plant(
                plot_id=plot_b.id,
                tenant_id=user_b.id,
                label="A1",
                row_label="A",
                row_order=0,
                col_order=0,
                visual_col=1,
            )
            db.add(plant_b)
            await db.flush()
            await db.commit()

            # A no ve la planta de B
            found = await get_plant(db, plant_b.id, tenant_id=user_a.id)
            assert found is None

            # A no ve plantas en la parcela de B aunque conozca el plot_id
            plants = await list_plants(db, plot_id=plot_b.id, tenant_id=user_a.id)
            assert plants == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_truffle_events_isolation(tmp_path: Path) -> None:
    """Los eventos de trufa del Usuario B no aparecen en el listado del Usuario A."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "ct_trufas.sqlite3")
    try:
        async with session_maker() as db:
            user_a = await _create_user(db, "user_a", "a@example.com")
            user_b = await _create_user(db, "user_b", "b@example.com")

            plot_b = await create_plot(
                db,
                tenant_id=user_b.id,
                name="P-B",
                polygon="1",
                plot_num="1",
                cadastral_ref="REF001",
                hydrant="H1",
                sector="S1",
                num_plants=2,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=None,
            )
            plant_b = Plant(
                plot_id=plot_b.id,
                tenant_id=user_b.id,
                label="A1",
                row_label="A",
                row_order=0,
                col_order=0,
                visual_col=1,
            )
            db.add(plant_b)
            await db.flush()

            await create_event(
                db,
                plant_id=plant_b.id,
                plot_id=plot_b.id,
                tenant_id=user_b.id,
                source="manual",
                dedupe_window_seconds=0,
            )
            await db.commit()

            events_a = await list_events(db, tenant_id=user_a.id)
            assert events_a == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_wells_isolation(tmp_path: Path) -> None:
    """El Usuario A no puede leer el pozo del Usuario B."""
    engine, session_maker = await _build_sessionmaker(tmp_path / "ct_wells.sqlite3")
    try:
        async with session_maker() as db:
            user_a = await _create_user(db, "user_a", "a@example.com")
            user_b = await _create_user(db, "user_b", "b@example.com")

            plot_b = await create_plot(
                db,
                tenant_id=user_b.id,
                name="P-B",
                polygon="1",
                plot_num="1",
                cadastral_ref="REF001",
                hydrant="H1",
                sector="S1",
                num_plants=2,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=None,
            )
            well_b = Well(
                tenant_id=user_b.id,
                plot_id=plot_b.id,
                date=datetime.date(2025, 6, 15),
                wells_per_plant=3,
            )
            db.add(well_b)
            await db.flush()
            await db.commit()

            # A intenta leer el pozo de B por ID → None
            found = await get_well(db, well_b.id, tenant_id=user_a.id)
            assert found is None

            # El listado de A no incluye pozos de B
            wells_a = await list_wells(db, tenant_id=user_a.id)
            assert wells_a == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_cross_tenant_irrigation_isolation(tmp_path: Path) -> None:
    """El Usuario A no puede leer el registro de riego del Usuario B."""
    engine, session_maker = await _build_sessionmaker(
        tmp_path / "ct_irrigation.sqlite3"
    )
    try:
        async with session_maker() as db:
            user_a = await _create_user(db, "user_a", "a@example.com")
            user_b = await _create_user(db, "user_b", "b@example.com")

            plot_b = await create_plot(
                db,
                tenant_id=user_b.id,
                name="P-B",
                polygon="1",
                plot_num="1",
                cadastral_ref="REF001",
                hydrant="H1",
                sector="S1",
                num_plants=2,
                planting_date=datetime.date(2020, 1, 1),
                area_ha=1.0,
                production_start=None,
            )
            irrigation_b = IrrigationRecord(
                tenant_id=user_b.id,
                plot_id=plot_b.id,
                date=datetime.date(2025, 7, 1),
                water_m3=15.0,
            )
            db.add(irrigation_b)
            await db.flush()
            await db.commit()

            # A intenta leer el riego de B por ID → None
            found = await get_irrigation_record(db, irrigation_b.id, tenant_id=user_a.id)
            assert found is None

            # El listado de A no incluye riegos de B
            records_a = await list_irrigation_records(db, tenant_id=user_a.id)
            assert records_a == []
    finally:
        await engine.dispose()

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Gasto, Ingreso, Parcela  # noqa: F401 - ensure metadata is loaded
from app.services.dashboard_service import build_dashboard_context
from app.services.gastos_service import create_gasto, get_gastos_list_context
from app.services.graficas_service import build_graficas_context
from app.services.ingresos_service import create_ingreso, get_ingresos_list_context
from app.services.parcelas_service import create_parcela, delete_parcela, get_parcela
from app.services.reportes_service import build_rentabilidad_context


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
            parcela = await create_parcela(
                db,
                nombre="Bancal Test",
                poligono="1",
                parcela_catastro="10",
                hidrante="H1",
                sector="S1",
                n_carrascas=50,
                fecha_plantacion=datetime.date(2021, 1, 1),
                superficie_ha=2.0,
                inicio_produccion=datetime.date(2024, 1, 1),
                porcentaje=100.0,
            )
            await db.commit()

            fetched = await get_parcela(db, parcela.id)
            assert fetched is not None
            assert fetched.nombre == "Bancal Test"

            await create_gasto(
                db,
                fecha=datetime.date(2025, 5, 10),
                concepto="Riego",
                persona="Javi",
                parcela_id=parcela.id,
                cantidad=25.0,
            )
            await create_ingreso(
                db,
                fecha=datetime.date(2025, 12, 10),
                parcela_id=parcela.id,
                cantidad_kg=2.0,
                categoria="A",
                euros_kg=50.0,
            )
            await db.commit()

            gastos_ctx = await get_gastos_list_context(db, 2025)
            ingresos_ctx = await get_ingresos_list_context(db, 2025)

            assert len(gastos_ctx["gastos"]) == 1
            assert gastos_ctx["total"] == 25.0
            assert len(ingresos_ctx["ingresos"]) == 1
            assert ingresos_ctx["total_euros"] == 100.0

            await delete_parcela(db, parcela)
            await db.commit()

            assert await get_parcela(db, parcela.id) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_dashboard_and_reportes_context_with_real_db(tmp_path: Path) -> None:
    engine, session_maker = await _build_sessionmaker(tmp_path / "reportes.sqlite3")

    try:
        async with session_maker() as db:
            p1 = await create_parcela(
                db,
                nombre="P1",
                poligono="1",
                parcela_catastro="1",
                hidrante="H1",
                sector="S1",
                n_carrascas=10,
                fecha_plantacion=datetime.date(2020, 1, 1),
                superficie_ha=1.0,
                inicio_produccion=datetime.date(2023, 1, 1),
                porcentaje=60.0,
            )
            p2 = await create_parcela(
                db,
                nombre="P2",
                poligono="2",
                parcela_catastro="2",
                hidrante="H2",
                sector="S2",
                n_carrascas=10,
                fecha_plantacion=datetime.date(2020, 1, 1),
                superficie_ha=1.0,
                inicio_produccion=datetime.date(2023, 1, 1),
                porcentaje=40.0,
            )

            await create_gasto(
                db,
                fecha=datetime.date(2025, 5, 1),
                concepto="Asignado",
                persona="A",
                parcela_id=p1.id,
                cantidad=100.0,
            )
            await create_gasto(
                db,
                fecha=datetime.date(2025, 5, 2),
                concepto="No asignado",
                persona="A",
                parcela_id=None,
                cantidad=50.0,
            )

            await create_ingreso(
                db,
                fecha=datetime.date(2025, 12, 1),
                parcela_id=p1.id,
                cantidad_kg=1.0,
                categoria="A",
                euros_kg=40.0,
            )
            await create_ingreso(
                db,
                fecha=datetime.date(2025, 12, 2),
                parcela_id=p2.id,
                cantidad_kg=1.0,
                categoria="A",
                euros_kg=30.0,
            )
            await db.commit()

            dashboard_ctx = await build_dashboard_context(db)
            report_ctx = await build_rentabilidad_context(db)

            assert dashboard_ctx["grand_gastos"] == 150.0
            assert dashboard_ctx["grand_ingresos"] == 70.0
            assert dashboard_ctx["grand_rentabilidad"] == -80.0
            assert len(dashboard_ctx["campaign_rows"]) == 1

            assert report_ctx["grand_total_ingresos"] == 70.0
            assert report_ctx["grand_total_gastos"] == 150.0
            assert report_ctx["grand_total_rentabilidad"] == -80.0
            assert report_ctx["all_years"] == [2025]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_graficas_context_with_real_db(tmp_path: Path) -> None:
    engine, session_maker = await _build_sessionmaker(tmp_path / "graficas.sqlite3")

    try:
        async with session_maker() as db:
            parcela = await create_parcela(
                db,
                nombre="PG",
                poligono="1",
                parcela_catastro="1",
                hidrante="H",
                sector="S",
                n_carrascas=10,
                fecha_plantacion=datetime.date(2020, 1, 1),
                superficie_ha=2.0,
                inicio_produccion=datetime.date(2023, 1, 1),
                porcentaje=100.0,
            )
            await create_gasto(
                db,
                fecha=datetime.date(2025, 11, 30),
                concepto="G",
                persona="X",
                parcela_id=parcela.id,
                cantidad=10.0,
            )
            await create_ingreso(
                db,
                fecha=datetime.date(2025, 12, 1),
                parcela_id=parcela.id,
                cantidad_kg=4.0,
                categoria="A",
                euros_kg=20.0,
            )
            await db.commit()

            ctx = await build_graficas_context(db, campaign=2025, bancal_id=parcela.id)

            assert ctx["selected_campaign"] == 2025
            assert ctx["selected_bancal"] == parcela.id
            assert json.loads(ctx["week_labels"]) != []
            assert json.loads(ctx["ing_values"]) == [80.0]
            assert json.loads(ctx["gas_values"]) == [10.0]
            assert len(ctx["kg_ha_table"]) == 1
    finally:
        await engine.dispose()

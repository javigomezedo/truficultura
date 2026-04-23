from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models import Plot, User  # noqa: F401
from app.models.rainfall import RainfallRecord  # noqa: F401
from app.schemas.rainfall import RainfallCreate
from app.services.plots_service import create_plot
from app.services.rainfall_service import (
    create_rainfall_record,
    delete_rainfall_record,
    get_rainfall_for_plot_on_date,
    get_rainfall_record,
    list_rainfall_records,
    update_rainfall_record,
)
from app.schemas.rainfall import RainfallUpdate


async def _build_sessionmaker(db_file: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_file}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    return engine, session_maker


@pytest.mark.asyncio
async def test_rainfall_crud_with_real_db(tmp_path: Path) -> None:
    engine, session_maker = await _build_sessionmaker(tmp_path / "rainfall.sqlite3")

    try:
        async with session_maker() as db:
            plot = await create_plot(
                db,
                user_id=1,
                name="Bancal Lluvia",
                polygon="1",
                plot_num="10",
                cadastral_ref="44223A021001200000FP",
                hydrant="H1",
                sector="S1",
                num_plants=50,
                planting_date=datetime.date(2021, 1, 1),
                area_ha=2.0,
                production_start=None,
            )
            await db.commit()

            # Create manual record linked to plot
            data = RainfallCreate(
                plot_id=plot.id,
                date=datetime.date(2025, 11, 10),
                precipitation_mm=15.0,
                source="manual",
            )
            record = await create_rainfall_record(db, user_id=1, data=data)
            await db.commit()

            assert record.id is not None
            assert record.plot_id == plot.id
            assert record.precipitation_mm == 15.0

            # Read back
            fetched = await get_rainfall_record(db, record.id, user_id=1)
            assert fetched is not None
            assert fetched.precipitation_mm == 15.0

            # List
            all_records = await list_rainfall_records(db, user_id=1)
            assert len(all_records) == 1

            # Update
            updated = await update_rainfall_record(
                db, record.id, user_id=1, data=RainfallUpdate(precipitation_mm=20.0)
            )
            await db.commit()
            assert updated.precipitation_mm == 20.0

            # Delete
            await delete_rainfall_record(db, record.id, user_id=1)
            await db.commit()

            gone = await get_rainfall_record(db, record.id, user_id=1)
            assert gone is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rainfall_priority_plot_over_municipio(tmp_path: Path) -> None:
    """Registro de parcela tiene prioridad sobre registro de municipio."""
    engine, session_maker = await _build_sessionmaker(
        tmp_path / "rainfall_priority.sqlite3"
    )

    try:
        async with session_maker() as db:
            plot = await create_plot(
                db,
                user_id=1,
                name="Bancal Sarrión",
                polygon="1",
                plot_num="11",
                cadastral_ref="44223A021001200000FP",
                hydrant="H2",
                sector="S1",
                num_plants=30,
                planting_date=datetime.date(2021, 1, 1),
                area_ha=1.5,
                production_start=None,
            )
            # Set municipio_cod manually on the plot
            plot.municipio_cod = "44216"
            await db.commit()

            date = datetime.date(2025, 11, 10)

            # Municipio-level record (AEMET)
            municipio_record = await create_rainfall_record(
                db,
                user_id=1,
                data=RainfallCreate(
                    municipio_cod="44216",
                    date=date,
                    precipitation_mm=8.0,
                    source="aemet",
                ),
            )
            await db.commit()

            # Without a plot-specific record, should return municipio record
            found = await get_rainfall_for_plot_on_date(db, plot, date, user_id=1)
            assert found is not None
            assert found.id == municipio_record.id
            assert found.precipitation_mm == 8.0

            # Now add a plot-specific record
            plot_record = await create_rainfall_record(
                db,
                user_id=1,
                data=RainfallCreate(
                    plot_id=plot.id,
                    date=date,
                    precipitation_mm=12.5,
                    source="manual",
                ),
            )
            await db.commit()

            # Now the plot-specific record should take priority
            found = await get_rainfall_for_plot_on_date(db, plot, date, user_id=1)
            assert found is not None
            assert found.id == plot_record.id
            assert found.precipitation_mm == 12.5
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_rainfall_user_isolation(tmp_path: Path) -> None:
    """Un usuario no puede ver los registros de otro usuario."""
    engine, session_maker = await _build_sessionmaker(
        tmp_path / "rainfall_isolation.sqlite3"
    )

    try:
        async with session_maker() as db:
            # Create record for user 1 (municipio level, no plot needed)
            await create_rainfall_record(
                db,
                user_id=1,
                data=RainfallCreate(
                    municipio_cod="44216",
                    date=datetime.date(2025, 11, 10),
                    precipitation_mm=10.0,
                    source="aemet",
                ),
            )
            await db.commit()

            # User 2 should see nothing
            records_user2 = await list_rainfall_records(db, user_id=2)
            assert records_user2 == []

            # User 1 should see their record
            records_user1 = await list_rainfall_records(db, user_id=1)
            assert len(records_user1) == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_list_rainfall_records_by_plot_excludes_municipio(
    tmp_path: Path,
) -> None:
    """Al filtrar list_rainfall_records por plot_id, solo aparecen los registros
    directamente ligados a esa parcela (plot_id=X). Los registros de municipio
    (ibericam/aemet, plot_id=NULL) no se mezclan — hay que filtrar por municipio_cod."""
    engine, session_maker = await _build_sessionmaker(
        tmp_path / "rainfall_plot_mun.sqlite3"
    )

    try:
        async with session_maker() as db:
            plot = await create_plot(
                db,
                user_id=1,
                name="Bancal Sarrión",
                polygon="1",
                plot_num="12",
                cadastral_ref="44223A021001200000FP",
                hydrant="H3",
                sector="S1",
                num_plants=40,
                planting_date=datetime.date(2021, 1, 1),
                area_ha=2.0,
                production_start=None,
            )
            plot.provincia_cod = "44"
            plot.municipio_cod = "210"
            await db.commit()

            # Registro manual ligado a la parcela
            manual = await create_rainfall_record(
                db,
                user_id=1,
                data=RainfallCreate(
                    plot_id=plot.id,
                    date=datetime.date(2025, 11, 10),
                    precipitation_mm=12.0,
                    source="manual",
                ),
            )

            # Registro ibericam a nivel de municipio (plot_id=None)
            ibericam = await create_rainfall_record(
                db,
                user_id=1,
                data=RainfallCreate(
                    municipio_cod="44210",
                    date=datetime.date(2025, 10, 1),
                    precipitation_mm=5.0,
                    source="ibericam",
                ),
            )
            await db.commit()

            # Filtro por parcela: solo el registro manual
            by_plot = await list_rainfall_records(db, user_id=1, plot_id=plot.id)
            ids_by_plot = {r.id for r in by_plot}
            assert manual.id in ids_by_plot, (
                "Registro manual debe aparecer al filtrar por parcela"
            )
            assert ibericam.id not in ids_by_plot, (
                "Registro de municipio NO debe mezclarse al filtrar por parcela"
            )

            # Filtro por municipio: solo el registro ibericam
            by_mun = await list_rainfall_records(db, user_id=1, municipio_cod="44210")
            ids_by_mun = {r.id for r in by_mun}
            assert ibericam.id in ids_by_mun, (
                "Registro ibericam debe aparecer al filtrar por municipio"
            )
            assert manual.id not in ids_by_mun, (
                "Registro de parcela NO debe mezclarse al filtrar por municipio"
            )
    finally:
        await engine.dispose()

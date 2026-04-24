#!/usr/bin/env python3
"""
Cron script: genera los gastos recurrentes vencidos para todos los usuarios.

Uso:
    uv run scripts/process_recurring_expenses_cron.py
    uv run scripts/process_recurring_expenses_cron.py --dry-run   # muestra qué haría sin escribir nada

Variables de entorno requeridas:
    DATABASE_URL   — URL de conexión a PostgreSQL (igual que en .env)
"""

import argparse
import asyncio
import logging
import os
import sys

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Asegura que el directorio raíz del proyecto está en el path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.recurring_expenses_service import process_recurring_expenses

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


async def main(dry_run: bool = False) -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL no definida. Abortando.")
        sys.exit(1)

    # Reutilizamos la normalización de config.py que ya maneja:
    # postgres:// → postgresql+asyncpg://, sslmode= → ssl=, etc.
    from app.config import Settings

    settings = Settings(DATABASE_URL=database_url)
    database_url = settings.SQLALCHEMY_DATABASE_URL

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)  # type: ignore[call-overload]

    try:
        async with async_session() as session:
            if dry_run:
                log.info(
                    "[DRY-RUN] Modo simulación activado — no se escribirá nada en la BD."
                )
                created = await process_recurring_expenses(session)
                log.info(
                    "[DRY-RUN] Se crearían %d gasto(s) recurrente(s). No se ha escrito nada.",
                    len(created),
                )
                for expense in created:
                    log.info(
                        "[DRY-RUN]  · user_id=%s | %s | %.2f € | %s",
                        expense.user_id,
                        expense.description,
                        expense.amount,
                        expense.date,
                    )
                await session.rollback()
            else:
                created = await process_recurring_expenses(session)
                await session.commit()
                log.info("Gastos recurrentes procesados: %d creados.", len(created))
    except Exception:
        log.exception("Error al procesar gastos recurrentes.")
        await engine.dispose()
        sys.exit(1)

    await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genera los gastos recurrentes vencidos para todos los usuarios."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué gastos crearía sin escribir nada en la base de datos.",
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))

"""Borra todos los datos de un tenant concreto.

Uso:
    uv run python scripts/clear_tenant_data.py <tenant_id>

El script elimina los datos en el orden correcto (hijos antes que padres)
respetando las foreign keys. El tenant y sus membresías NO se borran,
solo los datos de dominio.

Ejemplo:
    uv run python scripts/clear_tenant_data.py 3
"""

from __future__ import annotations

import asyncio
import sys

from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import settings
from app.models.brule import BruleRecord
from app.models.expense import Expense
from app.models.expense_proration_group import ExpenseProrationGroup
from app.models.income import Income
from app.models.irrigation import IrrigationRecord
from app.models.notification import Notification, NotificationPreference
from app.models.plant import Plant
from app.models.plant_presence import PlantPresence
from app.models.plot import Plot
from app.models.plot_event import PlotEvent
from app.models.plot_harvest import PlotHarvest
from app.models.rainfall import RainfallRecord
from app.models.recurring_expense import RecurringExpense
from app.models.truffle_event import TruffleEvent
from app.models.well import Well


# Tables ordered by dependency: children first, parents last.
_TABLES_ORDERED = [
    ("truffle_events", TruffleEvent),
    ("plant_presences", PlantPresence),
    ("brule_records", BruleRecord),
    ("plot_harvests", PlotHarvest),
    ("plot_events", PlotEvent),
    ("irrigation_records", IrrigationRecord),
    ("wells", Well),
    ("rainfall_records", RainfallRecord),
    ("notifications", Notification),
    ("notification_preferences", NotificationPreference),
    ("expense_proration_groups", ExpenseProrationGroup),
    ("expenses", Expense),
    ("recurring_expenses", RecurringExpense),
    ("incomes", Income),
    ("plants", Plant),
    ("plots", Plot),
]


async def clear_tenant(tenant_id: int) -> None:
    engine = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URL,
        echo=False,
        poolclass=NullPool,
    )
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with Session() as session:
        print(f"\nBorrando datos del tenant {tenant_id}...\n")
        total = 0

        for table_name, model in _TABLES_ORDERED:
            result = await session.execute(
                delete(model).where(model.tenant_id == tenant_id)
            )
            count = result.rowcount
            total += count
            if count:
                print(f"  {table_name:<30} {count:>5} filas borradas")
            else:
                print(f"  {table_name:<30}     - (vacía)")

        await session.commit()
        print(f"\nTotal: {total} filas borradas para tenant_id={tenant_id}.\n")

    await engine.dispose()


def main() -> None:
    args = sys.argv[1:]
    yes = "--yes" in args or "-y" in args
    args = [a for a in args if a not in ("--yes", "-y")]

    if len(args) != 1:
        print(__doc__)
        sys.exit(1)

    try:
        tenant_id = int(args[0])
    except ValueError:
        print(f"Error: '{args[0]}' no es un entero válido.")
        sys.exit(1)

    if not yes:
        confirm = (
            input(
                f"¿Seguro que quieres borrar TODOS los datos del tenant {tenant_id}? [s/N] "
            )
            .strip()
            .lower()
        )
        if confirm != "s":
            print("Cancelado.")
            sys.exit(0)

    asyncio.run(clear_tenant(tenant_id))


if __name__ == "__main__":
    main()

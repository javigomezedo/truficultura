from __future__ import annotations

import datetime
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.plot import Plot
from app.models.recurring_expense import FREQUENCIES, RecurringExpense

logger = logging.getLogger(__name__)


async def list_plots(db: AsyncSession, tenant_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.tenant_id == tenant_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def list_recurring_expenses(
    db: AsyncSession, tenant_id: int
) -> list[RecurringExpense]:
    result = await db.execute(
        select(RecurringExpense)
        .where(RecurringExpense.tenant_id == tenant_id)
        .order_by(RecurringExpense.description)
    )
    return result.scalars().all()


async def get_recurring_expense(
    db: AsyncSession, recurring_expense_id: int, tenant_id: int
) -> Optional[RecurringExpense]:
    result = await db.execute(
        select(RecurringExpense).where(
            RecurringExpense.id == recurring_expense_id,
            RecurringExpense.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_recurring_expense(
    db: AsyncSession,
    *,
    tenant_id: int,
    acting_user_id: Optional[int] = None,
    description: str,
    amount: float,
    category: Optional[str] = None,
    plot_id: Optional[int] = None,
    person: str = "",
    frequency: str = "monthly",
) -> RecurringExpense:
    obj = RecurringExpense(
        tenant_id=tenant_id,
        created_by_user_id=acting_user_id,
        description=description,
        amount=amount,
        category=category or None,
        plot_id=plot_id if plot_id else None,
        person=person,
        frequency=frequency if frequency in FREQUENCIES else "monthly",
        is_active=True,
        last_run_date=None,
    )
    db.add(obj)
    await db.flush()
    return obj


async def update_recurring_expense(
    db: AsyncSession,
    obj: RecurringExpense,
    *,
    acting_user_id: Optional[int] = None,
    description: str,
    amount: float,
    category: Optional[str] = None,
    plot_id: Optional[int] = None,
    person: str = "",
    frequency: str,
    is_active: bool,
) -> RecurringExpense:
    obj.description = description
    obj.amount = amount
    obj.category = category or None
    obj.plot_id = plot_id if plot_id else None
    obj.person = person
    obj.frequency = frequency if frequency in FREQUENCIES else "monthly"
    obj.is_active = is_active
    obj.updated_by_user_id = acting_user_id
    await db.flush()
    return obj


async def delete_recurring_expense(db: AsyncSession, obj: RecurringExpense) -> None:
    await db.delete(obj)
    await db.flush()


async def toggle_recurring_expense(
    db: AsyncSession, obj: RecurringExpense
) -> RecurringExpense:
    obj.is_active = not obj.is_active
    await db.flush()
    return obj


async def process_recurring_expenses(db: AsyncSession) -> list[Expense]:
    """
    Check all active recurring expenses and create Expense records where due.

    Frequencies:
    - weekly:  due if last_run_date is None or >= 7 days ago
    - monthly: due if last_run_date is None or from a previous month
    - annual:  due if last_run_date is None or from a previous year

    The generated Expense uses today as its date.

    Returns the list of Expense objects created.
    """
    today = datetime.date.today()
    result = await db.execute(
        select(RecurringExpense).where(RecurringExpense.is_active.is_(True))
    )
    actives = result.scalars().all()

    created: list[Expense] = []
    for rec in actives:
        if rec.last_run_date is None:
            due = True
        elif rec.frequency == "weekly":
            due = (today - rec.last_run_date).days >= 7
        elif rec.frequency == "annual":
            due = rec.last_run_date.year < today.year
        else:  # monthly (default)
            due = (rec.last_run_date.year, rec.last_run_date.month) < (today.year, today.month)

        if not due:
            continue

        expense = Expense(
            tenant_id=rec.tenant_id,
            created_by_user_id=None,
            date=today,
            description=rec.description,
            person=rec.person,
            plot_id=rec.plot_id,
            amount=rec.amount,
            category=rec.category,
        )
        db.add(expense)
        rec.last_run_date = today
        created.append(expense)
        logger.info(
            "Gasto recurrente creado: tenant_id=%s description=%r amount=%s date=%s",
            rec.tenant_id,
            rec.description,
            rec.amount,
            today,
        )

    if created:
        await db.flush()

    return created

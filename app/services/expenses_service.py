from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense import Expense
from app.models.plot import Plot
from app.utils import campaign_year, distribute_unassigned_expenses


async def list_plots(db: AsyncSession) -> list[Plot]:
    result = await db.execute(select(Plot).order_by(Plot.name))
    return result.scalars().all()


async def get_expense(db: AsyncSession, expense_id: int) -> Optional[Expense]:
    result = await db.execute(select(Expense).where(Expense.id == expense_id))
    return result.scalar_one_or_none()


async def get_expenses_list_context(db: AsyncSession, year: Optional[int]) -> dict:
    result = await db.execute(select(Expense).order_by(Expense.date.desc()))
    all_expenses = result.scalars().all()

    plots_result = await db.execute(select(Plot).order_by(Plot.name))
    all_plots = plots_result.scalars().all()

    years = sorted(set(campaign_year(e.date) for e in all_expenses), reverse=True)
    expenses = (
        [e for e in all_expenses if campaign_year(e.date) == year]
        if year
        else all_expenses
    )

    total = sum(e.amount for e in expenses)
    current_year = year or (
        campaign_year(datetime.date.today())
        if all_expenses
        else datetime.date.today().year
    )

    # Breakdown table: direct expenses + distributed general expenses per plot
    direct_by_plot: dict = {p.id: 0.0 for p in all_plots}
    general_total = 0.0
    for e in expenses:
        if e.plot_id is not None:
            direct_by_plot[e.plot_id] = direct_by_plot.get(e.plot_id, 0.0) + e.amount
        else:
            general_total += e.amount

    breakdown = []
    for p in all_plots:
        direct = direct_by_plot.get(p.id, 0.0)
        general_share = general_total * ((p.percentage or 0.0) / 100.0)
        breakdown.append(
            {
                "plot": p,
                "direct": direct,
                "general_share": general_share,
                "total": direct + general_share,
            }
        )

    return {
        "expenses": expenses,
        "plots": all_plots,
        "total": total,
        "years": years,
        "selected_year": year,
        "current_year": current_year,
        "breakdown": breakdown,
        "general_total": general_total,
    }


async def create_expense(
    db: AsyncSession,
    *,
    date: datetime.date,
    description: str,
    person: str,
    plot_id: Optional[int],
    amount: float,
) -> Expense:
    new_expense = Expense(
        date=date,
        description=description,
        person=person,
        plot_id=plot_id if plot_id else None,
        amount=amount,
    )
    db.add(new_expense)
    await db.flush()
    return new_expense


async def update_expense(
    db: AsyncSession,
    expense: Expense,
    *,
    date: datetime.date,
    description: str,
    person: str,
    plot_id: Optional[int],
    amount: float,
) -> Expense:
    expense.date = date
    expense.description = description
    expense.person = person
    expense.plot_id = plot_id if plot_id else None
    expense.amount = amount
    await db.flush()
    return expense


async def delete_expense(db: AsyncSession, expense: Expense) -> None:
    await db.delete(expense)
    await db.flush()

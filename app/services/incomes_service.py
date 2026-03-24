from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.income import Income
from app.models.plot import Plot
from app.utils import campaign_year


async def list_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def get_income(
    db: AsyncSession, income_id: int, user_id: int
) -> Optional[Income]:
    result = await db.execute(
        select(Income).where(Income.id == income_id, Income.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_incomes_list_context(
    db: AsyncSession, year: Optional[int], user_id: int
) -> dict:
    result = await db.execute(
        select(Income)
        .where(Income.user_id == user_id)
        .order_by(Income.date.desc(), Income.category)
    )
    all_incomes = result.scalars().all()

    years = sorted(set(campaign_year(i.date) for i in all_incomes), reverse=True)
    incomes = (
        [i for i in all_incomes if campaign_year(i.date) == year]
        if year
        else all_incomes
    )

    total_kg = sum(i.amount_kg for i in incomes)
    total_euros = sum(i.total for i in incomes)
    current_year = year or (
        campaign_year(datetime.date.today())
        if all_incomes
        else datetime.date.today().year
    )

    return {
        "incomes": incomes,
        "total_kg": total_kg,
        "total_euros": total_euros,
        "years": years,
        "selected_year": year,
        "current_year": current_year,
    }


async def create_income(
    db: AsyncSession,
    *,
    user_id: int,
    date: datetime.date,
    plot_id: Optional[int],
    amount_kg: float,
    category: str,
    euros_per_kg: float,
) -> Income:
    total = round(amount_kg * euros_per_kg, 2)
    new_income = Income(
        user_id=user_id,
        date=date,
        plot_id=plot_id if plot_id else None,
        amount_kg=amount_kg,
        category=category,
        euros_per_kg=euros_per_kg,
        total=total,
    )
    db.add(new_income)
    await db.flush()
    return new_income


async def update_income(
    db: AsyncSession,
    income: Income,
    *,
    date: datetime.date,
    plot_id: Optional[int],
    amount_kg: float,
    category: str,
    euros_per_kg: float,
) -> Income:
    total = round(amount_kg * euros_per_kg, 2)
    income.date = date
    income.plot_id = plot_id if plot_id else None
    income.amount_kg = amount_kg
    income.category = category
    income.euros_per_kg = euros_per_kg
    income.total = total
    await db.flush()
    return income


async def delete_income(db: AsyncSession, income: Income) -> None:
    await db.delete(income)
    await db.flush()

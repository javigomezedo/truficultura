from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.income import Income
from app.models.plot import Plot
from app.utils import campaign_year


async def list_plots(db: AsyncSession, tenant_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.tenant_id == tenant_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def get_income(
    db: AsyncSession, income_id: int, tenant_id: int
) -> Optional[Income]:
    result = await db.execute(
        select(Income).where(Income.id == income_id, Income.tenant_id == tenant_id)
    )
    return result.scalar_one_or_none()


async def get_incomes_list_context(
    db: AsyncSession,
    year: Optional[int],
    tenant_id: int,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    result = await db.execute(
        select(Income)
        .where(Income.tenant_id == tenant_id)
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

    _SORT_KEYS: dict = {
        "date": lambda x: x.date,
        "plot": lambda x: x.plot.name if x.plot else "",
        "amount_kg": lambda x: x.amount_kg,
        "category": lambda x: (x.category or "").lower(),
        "euros_per_kg": lambda x: x.euros_per_kg,
        "total": lambda x: x.total,
    }
    key_fn = _SORT_KEYS.get(sort_by, lambda x: x.date)
    incomes = sorted(incomes, key=key_fn, reverse=(sort_order == "desc"))

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
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


async def create_income(
    db: AsyncSession,
    *,
    tenant_id: int,
    acting_user_id: Optional[int] = None,
    date: datetime.date,
    plot_id: Optional[int],
    amount_kg: float,
    category: str,
    euros_per_kg: float,
) -> Income:
    new_income = Income(
        tenant_id=tenant_id,
        created_by_user_id=acting_user_id,
        date=date,
        plot_id=plot_id if plot_id else None,
        amount_kg=amount_kg,
        category=category,
        euros_per_kg=euros_per_kg,
    )
    db.add(new_income)
    await db.flush()
    return new_income


async def update_income(
    db: AsyncSession,
    income: Income,
    *,
    acting_user_id: Optional[int] = None,
    date: datetime.date,
    plot_id: Optional[int],
    amount_kg: float,
    category: str,
    euros_per_kg: float,
) -> Income:
    income.date = date
    income.plot_id = plot_id if plot_id else None
    income.amount_kg = amount_kg
    income.category = category
    income.euros_per_kg = euros_per_kg
    income.updated_by_user_id = acting_user_id
    await db.flush()
    return income


async def delete_income(db: AsyncSession, income: Income) -> None:
    await db.delete(income)
    await db.flush()

from __future__ import annotations

import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import _
from app.models.expense import Expense, EXPENSE_CATEGORIES
from app.models.expense_proration_group import ExpenseProrationGroup
from app.models.plot import Plot
from app.utils import campaign_year, distribute_unassigned_expenses

# Receipt validation constants
ALLOWED_RECEIPT_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
}
MAX_RECEIPT_SIZE = 5 * 1024 * 1024  # 5MB in bytes


async def list_plots(db: AsyncSession, user_id: int) -> list[Plot]:
    result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    return result.scalars().all()


async def get_expense(
    db: AsyncSession, expense_id: int, user_id: int
) -> Optional[Expense]:
    result = await db.execute(
        select(Expense).where(Expense.id == expense_id, Expense.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_expenses_list_context(
    db: AsyncSession,
    year: Optional[int],
    user_id: int,
    category: Optional[str] = None,
    person: Optional[str] = None,
    plot_id: Optional[int] = None,
    sort_by: str = "date",
    sort_order: str = "desc",
) -> dict:
    from sqlalchemy.orm import defer as sa_defer

    # Lightweight query for dropdown options (avoid loading all expense data).
    meta_result = await db.execute(
        select(Expense.date, Expense.person).where(Expense.user_id == user_id)
    )
    meta_rows = meta_result.all()
    years = sorted({campaign_year(r.date) for r in meta_rows}, reverse=True)
    people = sorted({r.person for r in meta_rows if r.person})

    plots_result = await db.execute(
        select(Plot).where(Plot.user_id == user_id).order_by(Plot.name)
    )
    all_plots = plots_result.scalars().all()

    # Build the filtered expense query — filter by campaign year at DB level.
    stmt = (
        select(Expense)
        .where(Expense.user_id == user_id)
        .options(sa_defer(Expense.receipt_data))
        .order_by(Expense.date.desc())
    )
    if year is not None:
        campaign_start = datetime.date(year, 5, 1)
        campaign_end = datetime.date(year + 1, 4, 30)
        stmt = stmt.where(Expense.date.between(campaign_start, campaign_end))
    if category:
        stmt = stmt.where(Expense.category == category)
    if person:
        stmt = stmt.where(Expense.person == person)
    if plot_id is not None:
        stmt = stmt.where(Expense.plot_id == plot_id)

    result = await db.execute(stmt)
    expenses = list(result.scalars().all())

    _SORT_KEYS: dict = {
        "date": lambda x: x.date,
        "description": lambda x: (x.description or "").lower(),
        "category": lambda x: (x.category or "").lower(),
        "person": lambda x: (x.person or "").lower(),
        "plot": lambda x: x.plot.name if x.plot else "",
        "amount": lambda x: x.amount,
    }
    key_fn = _SORT_KEYS.get(sort_by, lambda x: x.date)
    expenses.sort(key=key_fn, reverse=(sort_order == "desc"))

    total = sum(e.amount for e in expenses)
    current_year = year or campaign_year(datetime.date.today())

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
        "people": people,
        "selected_year": year,
        "selected_category": category,
        "selected_person": person,
        "selected_plot": plot_id,
        "current_year": current_year,
        "breakdown": breakdown,
        "general_total": general_total,
        "categories": EXPENSE_CATEGORIES,
        "sort_by": sort_by,
        "sort_order": sort_order,
    }


async def create_expense(
    db: AsyncSession,
    *,
    user_id: int,
    date: datetime.date,
    description: str,
    person: str,
    plot_id: Optional[int],
    amount: float,
    category: Optional[str] = None,
) -> Expense:
    new_expense = Expense(
        user_id=user_id,
        date=date,
        description=description,
        person=person,
        plot_id=plot_id if plot_id else None,
        amount=amount,
        category=category or None,
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
    category: Optional[str] = None,
) -> Expense:
    expense.date = date
    expense.description = description
    expense.person = person
    expense.plot_id = plot_id if plot_id else None
    expense.amount = amount
    expense.category = category or None
    await db.flush()
    return expense


async def delete_expense(db: AsyncSession, expense: Expense) -> None:
    await db.delete(expense)
    await db.flush()


async def create_prorated_expense(
    db: AsyncSession,
    *,
    user_id: int,
    date: datetime.date,
    description: str,
    person: str,
    plot_id: Optional[int],
    amount: float,
    category: Optional[str] = None,
    years: int,
    start_year: int,
) -> ExpenseProrationGroup:
    """Create a prorated expense spread over N years.

    Creates one ExpenseProrationGroup and N Expense records, one per year
    starting from start_year. The per-year amount is rounded to 2 decimals;
    the last entry absorbs any rounding difference so the total is exact.
    """
    group = ExpenseProrationGroup(
        user_id=user_id,
        description=description,
        total_amount=amount,
        years=years,
        start_year=start_year,
    )
    db.add(group)
    await db.flush()  # obtain group.id before creating child expenses

    per_year = round(amount / years, 2)
    for i in range(years):
        if i < years - 1:
            year_amount = per_year
        else:
            # Last entry absorbs rounding difference
            year_amount = round(amount - per_year * (years - 1), 2)

        expense = Expense(
            user_id=user_id,
            date=datetime.date(start_year + i, 1, 1),
            description=description,
            person=person,
            plot_id=plot_id if plot_id else None,
            amount=year_amount,
            category=category or None,
            proration_group_id=group.id,
        )
        db.add(expense)

    await db.flush()
    return group


async def get_proration_group(
    db: AsyncSession, group_id: int, user_id: int
) -> Optional[ExpenseProrationGroup]:
    """Fetch a proration group by id, filtered by user_id."""
    result = await db.execute(
        select(ExpenseProrationGroup).where(
            ExpenseProrationGroup.id == group_id,
            ExpenseProrationGroup.user_id == user_id,
        )
    )
    return result.scalar_one_or_none()


async def delete_proration_group(
    db: AsyncSession, group: ExpenseProrationGroup
) -> None:
    """Delete a proration group and all its child expenses (via DB cascade)."""
    await db.delete(group)
    await db.flush()


async def save_receipt(
    db: AsyncSession,
    expense: Expense,
    filename: str,
    file_data: bytes,
    content_type: str,
) -> None:
    """
    Save a receipt file to an expense.

    Args:
        db: Database session
        expense: Expense object to attach receipt to
        filename: Original filename (e.g., "invoice.pdf")
        file_data: Binary file content
        content_type: MIME type of the file

    Raises:
        ValueError: If file type not allowed or file too large
    """
    # Validate content type
    if content_type not in ALLOWED_RECEIPT_TYPES:
        raise ValueError(
            _(
                "Tipo de archivo no permitido: {content_type}. Permitidos: PDF e imágenes (JPEG, PNG, GIF, WebP)",
                content_type=content_type,
            )
        )

    # Validate file size
    if len(file_data) > MAX_RECEIPT_SIZE:
        raise ValueError(
            _(
                "Archivo demasiado grande. Máximo: 5MB, Tamaño actual: {size_mb:.1f}MB",
                size_mb=len(file_data) / (1024 * 1024),
            )
        )

    expense.receipt_filename = filename
    expense.receipt_data = file_data
    expense.receipt_content_type = content_type
    await db.flush()


async def get_receipt(
    db: AsyncSession, expense_id: int, user_id: int
) -> Optional[tuple[str, bytes, str]]:
    """
    Retrieve a receipt from an expense.

    Returns:
        Tuple of (filename, file_data, content_type) if receipt exists, None otherwise
    """
    expense = await get_expense(db, expense_id, user_id)
    if expense is None or expense.receipt_data is None:
        return None

    return (
        expense.receipt_filename or "receipt",
        expense.receipt_data,
        expense.receipt_content_type or "application/octet-stream",
    )


async def delete_receipt(db: AsyncSession, expense: Expense) -> None:
    """Delete a receipt from an expense."""
    expense.receipt_filename = None
    expense.receipt_data = None
    expense.receipt_content_type = None
    await db.flush()

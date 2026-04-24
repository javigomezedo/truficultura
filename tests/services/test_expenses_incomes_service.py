from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.i18n import set_locale
from app.models.expense import Expense
from app.models.income import Income
from app.services.expenses_service import (
    create_expense,
    create_prorated_expense,
    delete_expense,
    delete_proration_group,
    delete_receipt,
    get_expense,
    get_expenses_list_context,
    get_proration_group,
    get_receipt,
    save_receipt,
    update_expense,
)
from app.services.incomes_service import (
    create_income,
    delete_income,
    get_income,
    get_incomes_list_context,
    update_income,
)
from tests.conftest import result


@pytest.mark.asyncio
async def test_expenses_list_context_filters_by_campaign() -> None:
    expenses = [
        Expense(id=1, date=datetime.date(2025, 5, 1), description="A", amount=10.0),
        Expense(id=2, date=datetime.date(2026, 2, 1), description="B", amount=5.0),
    ]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result(expenses), result([])])

    context = await get_expenses_list_context(db, 2025, user_id=1)

    assert context["selected_year"] == 2025
    assert len(context["expenses"]) == 2
    assert context["total"] == 15.0
    assert 2025 in context["years"]


@pytest.mark.asyncio
async def test_expenses_list_context_filters_by_plot() -> None:
    expenses = [
        Expense(
            id=1,
            date=datetime.date(2025, 6, 1),
            description="Con bancal",
            amount=12.0,
            plot_id=10,
        ),
        Expense(
            id=2,
            date=datetime.date(2025, 6, 2),
            description="Sin bancal",
            amount=8.0,
            plot_id=None,
        ),
    ]
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[result(expenses), result([])])

    context = await get_expenses_list_context(db, 2025, user_id=1, plot_id=10)

    assert context["selected_plot"] == 10
    assert len(context["expenses"]) == 1
    assert context["expenses"][0].id == 1
    assert context["total"] == 12.0


@pytest.mark.asyncio
async def test_incomes_list_context_filters_by_campaign() -> None:
    incomes = [
        Income(
            id=1,
            date=datetime.date(2025, 6, 1),
            amount_kg=2.0,
            euros_per_kg=10.0,
            total=20.0,
        ),
        Income(
            id=2,
            date=datetime.date(2026, 1, 15),
            amount_kg=1.0,
            euros_per_kg=15.0,
            total=15.0,
        ),
    ]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result(incomes))

    context = await get_incomes_list_context(db, 2025, user_id=1)

    assert context["selected_year"] == 2025
    assert len(context["incomes"]) == 2
    assert context["total_kg"] == 3.0
    assert context["total_euros"] == 35.0


@pytest.mark.asyncio
async def test_create_update_delete_expense() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    expense = await create_expense(
        db,
        date=datetime.date(2025, 7, 1),
        description="Riego",
        person="Javi",
        plot_id=1,
        amount=50.0,
        user_id=1,
    )
    assert expense.plot_id == 1

    await update_expense(
        db,
        expense,
        date=datetime.date(2025, 8, 1),
        description="Riego 2",
        person="Javi",
        plot_id=None,
        amount=75.0,
    )
    assert expense.plot_id is None
    assert expense.amount == 75.0

    await delete_expense(db, expense)
    db.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_update_delete_income() -> None:
    db = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()

    income = await create_income(
        db,
        date=datetime.date(2025, 11, 1),
        plot_id=2,
        amount_kg=3.0,
        category="A",
        euros_per_kg=100.0,
        user_id=1,
    )
    assert income.total == 300.0

    await update_income(
        db,
        income,
        date=datetime.date(2025, 11, 2),
        plot_id=None,
        amount_kg=4.0,
        category="B",
        euros_per_kg=80.0,
    )
    assert income.total == 320.0
    assert income.plot_id is None

    await delete_income(db, income)
    db.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_expense_and_get_income() -> None:
    expense = Expense(
        id=10, date=datetime.date(2025, 1, 1), description="X", amount=1.0
    )
    income = Income(
        id=20,
        date=datetime.date(2025, 1, 1),
        amount_kg=1.0,
        euros_per_kg=1.0,
        total=1.0,
    )

    db_e = MagicMock()
    db_e.execute = AsyncMock(return_value=result([expense]))
    assert await get_expense(db_e, 10, user_id=1) is expense

    db_i = MagicMock()
    db_i.execute = AsyncMock(return_value=result([income]))
    assert await get_income(db_i, 20, user_id=1) is income


@pytest.mark.asyncio
async def test_save_receipt_valid_pdf() -> None:
    """Test saving a valid PDF receipt."""
    expense = Expense(
        id=1, date=datetime.date(2025, 1, 1), description="Invoice", amount=100.0
    )
    db = MagicMock()
    db.flush = AsyncMock()

    pdf_data = b"%PDF-1.4\n%fake pdf content"
    await save_receipt(
        db,
        expense,
        filename="invoice.pdf",
        file_data=pdf_data,
        content_type="application/pdf",
    )

    assert expense.receipt_filename == "invoice.pdf"
    assert expense.receipt_data == pdf_data
    assert expense.receipt_content_type == "application/pdf"
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_save_receipt_valid_image() -> None:
    """Test saving a valid image receipt."""
    expense = Expense(
        id=1, date=datetime.date(2025, 1, 1), description="Invoice", amount=100.0
    )
    db = MagicMock()
    db.flush = AsyncMock()

    image_data = b"\x89PNG\r\n\x1a\n"  # PNG header
    await save_receipt(
        db,
        expense,
        filename="receipt.png",
        file_data=image_data,
        content_type="image/png",
    )

    assert expense.receipt_filename == "receipt.png"
    assert expense.receipt_data == image_data
    assert expense.receipt_content_type == "image/png"


@pytest.mark.asyncio
async def test_save_receipt_invalid_content_type() -> None:
    """Test that invalid content types are rejected."""
    expense = Expense(
        id=1, date=datetime.date(2025, 1, 1), description="Invoice", amount=100.0
    )
    db = MagicMock()

    with pytest.raises(ValueError, match="Tipo de archivo no permitido"):
        await save_receipt(
            db,
            expense,
            filename="script.exe",
            file_data=b"malicious",
            content_type="application/x-exe",
        )


@pytest.mark.asyncio
async def test_save_receipt_file_too_large() -> None:
    """Test that oversized files are rejected."""
    expense = Expense(
        id=1, date=datetime.date(2025, 1, 1), description="Invoice", amount=100.0
    )
    db = MagicMock()

    # Create data larger than 5MB
    large_data = b"x" * (6 * 1024 * 1024)

    with pytest.raises(ValueError, match="Archivo demasiado grande"):
        await save_receipt(
            db,
            expense,
            filename="large.pdf",
            file_data=large_data,
            content_type="application/pdf",
        )


@pytest.mark.asyncio
async def test_save_receipt_invalid_content_type_is_translated_in_english() -> None:
    expense = Expense(
        id=1, date=datetime.date(2025, 1, 1), description="Invoice", amount=100.0
    )
    db = MagicMock()

    set_locale("en")
    try:
        with pytest.raises(ValueError, match="File type not allowed"):
            await save_receipt(
                db,
                expense,
                filename="script.exe",
                file_data=b"malicious",
                content_type="application/x-exe",
            )
    finally:
        set_locale("es")


@pytest.mark.asyncio
async def test_get_receipt_exists() -> None:
    """Test retrieving an existing receipt."""
    expense = Expense(
        id=1,
        date=datetime.date(2025, 1, 1),
        description="Invoice",
        amount=100.0,
        receipt_filename="invoice.pdf",
        receipt_data=b"pdf content",
        receipt_content_type="application/pdf",
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([expense]))

    receipt_data = await get_receipt(db, 1, user_id=1)

    assert receipt_data is not None
    filename, data, content_type = receipt_data
    assert filename == "invoice.pdf"
    assert data == b"pdf content"
    assert content_type == "application/pdf"


@pytest.mark.asyncio
async def test_get_receipt_not_found() -> None:
    """Test retrieving a receipt when expense does not exist."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    receipt_data = await get_receipt(db, 999, user_id=1)

    assert receipt_data is None


@pytest.mark.asyncio
async def test_get_receipt_no_data() -> None:
    """Test retrieving when receipt data is None."""
    expense = Expense(
        id=1,
        date=datetime.date(2025, 1, 1),
        description="Invoice",
        amount=100.0,
        receipt_filename=None,
        receipt_data=None,
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([expense]))

    receipt_data = await get_receipt(db, 1, user_id=1)

    assert receipt_data is None


@pytest.mark.asyncio
async def test_delete_receipt() -> None:
    """Test deleting a receipt from an expense."""
    expense = Expense(
        id=1,
        date=datetime.date(2025, 1, 1),
        description="Invoice",
        amount=100.0,
        receipt_filename="invoice.pdf",
        receipt_data=b"pdf content",
    )
    db = MagicMock()
    db.flush = AsyncMock()

    await delete_receipt(db, expense)

    assert expense.receipt_filename is None
    assert expense.receipt_data is None
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_prorated_expense_creates_group_and_entries() -> None:
    """create_prorated_expense should create 1 group + N expense rows."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    from app.models.expense_proration_group import ExpenseProrationGroup

    group = await create_prorated_expense(
        db,
        user_id=1,
        date=datetime.date(2025, 6, 15),
        description="Instalación riego",
        person="",
        plot_id=None,
        amount=300.0,
        category="irrigation",
        years=3,
        start_year=2025,
    )

    # db.add called once for the group + 3 times for expenses = 4 total
    assert db.add.call_count == 4
    # first add is the group
    first_call_arg = db.add.call_args_list[0][0][0]
    assert isinstance(first_call_arg, ExpenseProrationGroup)
    assert first_call_arg.years == 3
    assert first_call_arg.start_year == 2025
    assert first_call_arg.total_amount == 300.0
    # db.flush called twice (after group creation and after expenses)
    assert db.flush.await_count == 2


@pytest.mark.asyncio
async def test_create_prorated_expense_rounding_absorbed_by_last() -> None:
    """Last expense entry absorbs any rounding difference."""
    db = MagicMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    await create_prorated_expense(
        db,
        user_id=1,
        date=datetime.date(2025, 1, 1),
        description="Test redondeo",
        person="",
        plot_id=None,
        amount=100.0,
        category="other",
        years=3,
        start_year=2025,
    )

    # 100 / 3 = 33.33 per year; last entry = 100 - 33.33*2 = 33.34
    expense_calls = db.add.call_args_list[1:]  # skip group
    amounts = [call[0][0].amount for call in expense_calls]
    assert amounts[0] == 33.33
    assert amounts[1] == 33.33
    assert abs(amounts[2] - 33.34) < 0.001
    assert abs(sum(amounts) - 100.0) < 0.001


@pytest.mark.asyncio
async def test_get_proration_group_returns_group() -> None:
    from app.models.expense_proration_group import ExpenseProrationGroup

    group = ExpenseProrationGroup(
        id=5, user_id=1, description="X", total_amount=200.0, years=2, start_year=2025
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([group]))

    fetched = await get_proration_group(db, group_id=5, user_id=1)
    assert fetched is group


@pytest.mark.asyncio
async def test_get_proration_group_returns_none_when_not_found() -> None:
    db = MagicMock()
    db.execute = AsyncMock(return_value=result([]))

    fetched = await get_proration_group(db, group_id=999, user_id=1)
    assert fetched is None


@pytest.mark.asyncio
async def test_delete_proration_group_calls_db_delete() -> None:
    from app.models.expense_proration_group import ExpenseProrationGroup

    group = ExpenseProrationGroup(
        id=3, user_id=1, description="Y", total_amount=100.0, years=2, start_year=2024
    )
    db = MagicMock()
    db.delete = AsyncMock()
    db.flush = AsyncMock()

    await delete_proration_group(db, group)

    db.delete.assert_awaited_once_with(group)
    db.flush.assert_awaited_once()

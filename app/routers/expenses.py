import datetime
from io import BytesIO
from typing import Optional
from urllib.parse import quote, quote_plus

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.i18n import _
from app.models.expense import EXPENSE_CATEGORIES
from app.models.user import User
from app.services.expenses_service import (
    create_expense as create_expense_service,
    delete_expense as delete_expense_service,
    delete_receipt,
    get_expense,
    get_expenses_list_context,
    get_receipt,
    list_plots,
    save_receipt,
    update_expense as update_expense_service,
)

router = APIRouter(prefix="/expenses", tags=["expenses"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def list_expenses(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
    year: Optional[str] = Query(default=None),
    plot_id: Optional[str] = Query(default=None),
    category: Optional[str] = None,
    person: Optional[str] = None,
    msg: Optional[str] = None,
    sort: Optional[str] = Query(default=None),
    order: Optional[str] = Query(default=None),
):
    year_int = int(year) if year else None
    plot_id_int = int(plot_id) if plot_id else None
    context = await get_expenses_list_context(
        db,
        year_int,
        current_user.id,
        category=category,
        person=person,
        plot_id=plot_id_int,
        sort_by=sort or "date",
        sort_order=order if order in ("asc", "desc") else "desc",
    )

    return templates.TemplateResponse(
        request,
        "gastos/list.html",
        {
            "request": request,
            **context,
            "msg": msg,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_expense_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    plots = await list_plots(db, current_user.id)
    return templates.TemplateResponse(
        request,
        "gastos/form.html",
        {
            "request": request,
            "expense": None,
            "plots": plots,
            "categories": EXPENSE_CATEGORIES,
            "action": "/expenses/",
            "method": "post",
        },
    )


@router.post("/", response_class=RedirectResponse)
async def create_expense(
    request: Request,
    date: datetime.date = Form(...),
    description: str = Form(...),
    person: str = Form(""),
    plot_id: Optional[int] = Form(None),
    amount: float = Form(0.0),
    category: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    await create_expense_service(
        db,
        user_id=current_user.id,
        date=date,
        description=description,
        person=person,
        plot_id=plot_id,
        amount=amount,
        category=category,
    )
    return RedirectResponse(
        url=f"/expenses/?msg={quote_plus(_('Gasto registrado correctamente'))}",
        status_code=303,
    )


@router.get("/{expense_id}/edit", response_class=HTMLResponse)
async def edit_expense_form(
    request: Request,
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    expense = await get_expense(db, expense_id, current_user.id)
    if expense is None:
        return RedirectResponse(
            url=f"/expenses/?msg={quote_plus(_('Gasto no encontrado'))}",
            status_code=303,
        )

    plots = await list_plots(db, current_user.id)

    return templates.TemplateResponse(
        request,
        "gastos/form.html",
        {
            "request": request,
            "expense": expense,
            "plots": plots,
            "categories": EXPENSE_CATEGORIES,
            "action": f"/expenses/{expense_id}",
            "method": "post",
        },
    )


@router.post("/{expense_id}", response_class=RedirectResponse)
async def update_expense(
    request: Request,
    expense_id: int,
    date: datetime.date = Form(...),
    description: str = Form(...),
    person: str = Form(""),
    plot_id: Optional[int] = Form(None),
    amount: float = Form(0.0),
    category: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    obj = await get_expense(db, expense_id, current_user.id)
    if obj is None:
        return RedirectResponse(
            url=f"/expenses/?msg={quote_plus(_('Gasto no encontrado'))}",
            status_code=303,
        )

    await update_expense_service(
        db,
        obj,
        date=date,
        description=description,
        person=person,
        plot_id=plot_id,
        amount=amount,
        category=category,
    )
    return RedirectResponse(
        url=f"/expenses/?msg={quote_plus(_('Gasto actualizado correctamente'))}",
        status_code=303,
    )


@router.post("/{expense_id}/delete", response_class=RedirectResponse)
async def delete_expense(
    request: Request,
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    obj = await get_expense(db, expense_id, current_user.id)
    if obj:
        await delete_expense_service(db, obj)
    return RedirectResponse(
        url=f"/expenses/?msg={quote_plus(_('Gasto eliminado correctamente'))}",
        status_code=303,
    )


@router.post("/{expense_id}/receipt", response_class=RedirectResponse)
async def upload_receipt(
    request: Request,
    expense_id: int,
    receipt: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Upload a receipt file to an expense."""
    obj = await get_expense(db, expense_id, current_user.id)
    if obj is None:
        return RedirectResponse(
            url=f"/expenses/?msg={quote_plus(_('Gasto no encontrado'))}",
            status_code=303,
        )

    try:
        file_data = await receipt.read()
        content_type = receipt.content_type or "application/octet-stream"

        await save_receipt(
            db,
            obj,
            filename=receipt.filename or "receipt",
            file_data=file_data,
            content_type=content_type,
        )
        return RedirectResponse(
            url=(
                f"/expenses/{expense_id}/edit?msg="
                f"{quote_plus(_('Recibo cargado correctamente'))}"
            ),
            status_code=303,
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/expenses/{expense_id}/edit?msg={quote_plus(str(e))}",
            status_code=303,
        )


@router.get("/{expense_id}/receipt/download")
async def download_receipt(
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Download a receipt file from an expense."""
    receipt_data = await get_receipt(db, expense_id, current_user.id)
    if receipt_data is None:
        return RedirectResponse(
            url=f"/expenses/?msg={quote_plus(_('Recibo no encontrado'))}",
            status_code=303,
        )

    filename, file_content, content_type = receipt_data
    return StreamingResponse(
        BytesIO(file_content),
        media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{quote(filename)}"'},
    )


@router.post("/{expense_id}/receipt/delete", response_class=RedirectResponse)
async def delete_expense_receipt(
    request: Request,
    expense_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    """Delete a receipt from an expense."""
    obj = await get_expense(db, expense_id, current_user.id)
    if obj is None:
        return RedirectResponse(
            url=f"/expenses/?msg={quote_plus(_('Gasto no encontrado'))}",
            status_code=303,
        )

    await delete_receipt(db, obj)
    return RedirectResponse(
        url=(
            f"/expenses/{expense_id}/edit?msg="
            f"{quote_plus(_('Recibo eliminado correctamente'))}"
        ),
        status_code=303,
    )

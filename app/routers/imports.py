from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.database import get_db
from app.models.user import User
from app.services.import_service import (
    import_expenses_csv,
    import_incomes_csv,
    import_irrigation_csv,
    import_plots_csv,
    import_truffles_csv,
    import_wells_csv,
)

router = APIRouter(prefix="/import", tags=["import"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def import_page(
    request: Request,
    current_user: User = Depends(require_user),
):
    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {"request": request, "result": None},
    )


@router.post("/expenses", response_class=HTMLResponse)
async def upload_expenses(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    content = await file.read()
    rows, warnings = await import_expenses_csv(db, content, current_user.id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "expenses",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "expenses",
        },
    )


@router.post("/incomes", response_class=HTMLResponse)
async def upload_incomes(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    content = await file.read()
    rows, warnings = await import_incomes_csv(db, content, current_user.id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "incomes",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "incomes",
        },
    )


@router.post("/plots", response_class=HTMLResponse)
async def upload_plots(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    content = await file.read()
    rows, warnings = await import_plots_csv(db, content, current_user.id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "plots",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "plots",
        },
    )


@router.post("/irrigation", response_class=HTMLResponse)
async def upload_irrigation(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    content = await file.read()
    rows, warnings = await import_irrigation_csv(db, content, current_user.id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "irrigation",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "irrigation",
        },
    )


@router.post("/wells", response_class=HTMLResponse)
async def upload_wells(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    content = await file.read()
    rows, warnings = await import_wells_csv(db, content, current_user.id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "wells",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "wells",
        },
    )


@router.post("/truffles", response_class=HTMLResponse)
async def upload_truffles(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
):
    content = await file.read()
    rows, warnings = await import_truffles_csv(db, content, current_user.id)
    await db.commit()

    return templates.TemplateResponse(
        request,
        "imports/index.html",
        {
            "request": request,
            "result": {
                "type": "truffles",
                "filename": file.filename,
                "imported": len(rows),
                "warnings": warnings,
            },
            "active_tab": "truffles",
        },
    )

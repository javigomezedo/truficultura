from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_subscription
from app.database import get_db
from app.main import app


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True)


def _db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    return db


def test_expenses_list_renders(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.expenses.get_expenses_list_context",
        AsyncMock(
            return_value={
                "expenses": [],
                "plots": [],
                "years": [],
                "selected_year": None,
                "selected_category": None,
                "selected_person": None,
                "selected_plot": None,
                "total": 0,
                "breakdown": [],
                "general_total": 0,
                "categories": [],
                "people": [],
                "sort_by": "date",
                "sort_order": "desc",
            }
        ),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/expenses/?msg=ok")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Gastos" in response.text


def test_expenses_list_forwards_plot_filter(monkeypatch) -> None:
    fake_db = _db()
    context_mock = AsyncMock(
        return_value={
            "expenses": [],
            "plots": [],
            "years": [],
            "selected_year": None,
            "selected_category": None,
            "selected_person": None,
            "selected_plot": 7,
            "total": 0,
            "breakdown": [],
            "general_total": 0,
            "categories": [],
            "people": [],
            "sort_by": "date",
            "sort_order": "desc",
        }
    )
    monkeypatch.setattr("app.routers.expenses.get_expenses_list_context", context_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/expenses/?plot_id=7")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    context_mock.assert_awaited_once()
    kwargs = context_mock.await_args.kwargs
    assert kwargs["plot_id"] == 7


def test_create_expense_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.expenses.create_expense_service", AsyncMock())
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/expenses/",
            data={
                "date": "2025-11-15",
                "description": "Poda",
                "person": "Javi",
                "amount": "10.5",
                "category": "Poda",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Gasto+registrado+correctamente" in response.headers["location"]


def test_new_expense_form_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.expenses.list_plots", AsyncMock(return_value=[]))
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/expenses/new")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "<form" in response.text


def test_edit_expense_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=None)
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/expenses/123/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Gasto+no+encontrado" in response.headers["location"]


def test_edit_expense_form_renders(monkeypatch) -> None:
    fake_db = _db()
    expense = SimpleNamespace(
        id=22, description="Poda", date=datetime.date(2025, 11, 15)
    )
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=expense)
    )
    monkeypatch.setattr("app.routers.expenses.list_plots", AsyncMock(return_value=[]))
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/expenses/22/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Poda" in response.text


def test_update_expense_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=None)
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/expenses/123",
            data={
                "date": "2025-11-15",
                "description": "Poda",
                "person": "Javi",
                "amount": "10.5",
                "category": "Poda",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Gasto+no+encontrado" in response.headers["location"]


def test_update_expense_redirects(monkeypatch) -> None:
    fake_db = _db()
    expense = SimpleNamespace(id=22)
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=expense)
    )
    monkeypatch.setattr("app.routers.expenses.update_expense_service", AsyncMock())
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/expenses/22",
            data={
                "date": "2025-11-16",
                "description": "Poda 2",
                "person": "Javi",
                "amount": "22.0",
                "category": "Poda",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Gasto+actualizado+correctamente" in response.headers["location"]


def test_delete_expense_redirects_even_when_not_found(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=None)
    )
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.expenses.delete_expense_service", delete_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/expenses/22/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Gasto+eliminado+correctamente" in response.headers["location"]
    delete_mock.assert_not_called()


def test_delete_expense_calls_service_when_found(monkeypatch) -> None:
    fake_db = _db()
    expense = SimpleNamespace(id=22)
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=expense)
    )
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.expenses.delete_expense_service", delete_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/expenses/22/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    delete_mock.assert_awaited_once()


def test_upload_receipt_value_error_redirects(monkeypatch) -> None:
    fake_db = _db()
    expense = SimpleNamespace(id=10)
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=expense)
    )
    monkeypatch.setattr(
        "app.routers.expenses.save_receipt",
        AsyncMock(side_effect=ValueError("archivo demasiado grande")),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/expenses/10/receipt",
            files={"receipt": ("factura.pdf", b"pdf", "application/pdf")},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "archivo+demasiado+grande" in response.headers["location"]


def test_upload_receipt_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=None)
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/expenses/10/receipt",
            files={"receipt": ("factura.pdf", b"pdf", "application/pdf")},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Gasto+no+encontrado" in response.headers["location"]


def test_upload_receipt_success_redirects(monkeypatch) -> None:
    fake_db = _db()
    expense = SimpleNamespace(id=10)
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=expense)
    )
    save_mock = AsyncMock()
    monkeypatch.setattr("app.routers.expenses.save_receipt", save_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/expenses/10/receipt",
            files={"receipt": ("factura.pdf", b"pdf", "application/pdf")},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Recibo+cargado+correctamente" in response.headers["location"]
    save_mock.assert_awaited_once()


def test_download_receipt_streams_file(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.expenses.get_receipt",
        AsyncMock(return_value=("factura.pdf", b"contenido", "application/pdf")),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/expenses/10/receipt/download")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'inline; filename="factura.pdf"'
    assert response.content == b"contenido"


def test_download_receipt_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.expenses.get_receipt", AsyncMock(return_value=None)
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/expenses/10/receipt/download", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Recibo+no+encontrado" in response.headers["location"]


def test_delete_receipt_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=None)
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/expenses/10/receipt/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Gasto+no+encontrado" in response.headers["location"]


def test_delete_receipt_success_redirects(monkeypatch) -> None:
    fake_db = _db()
    expense = SimpleNamespace(id=10)
    monkeypatch.setattr(
        "app.routers.expenses.get_expense", AsyncMock(return_value=expense)
    )
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.expenses.delete_receipt", delete_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/expenses/10/receipt/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Recibo+eliminado+correctamente" in response.headers["location"]
    delete_mock.assert_awaited_once()

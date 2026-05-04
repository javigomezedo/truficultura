from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_subscription
from app.database import get_db
from app.main import app


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True, active_tenant_id=1)


def _db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    return db


def _make_rec(
    id=1,
    description="Regadío Social",
    amount=50.0,
    category="Regadío Social",
    plot_id=None,
    plot=None,
    person="",
    frequency="monthly",
    is_active=True,
    last_run_date=None,
):
    obj = MagicMock()
    obj.id = id
    obj.description = description
    obj.amount = amount
    obj.category = category
    obj.plot_id = plot_id
    obj.plot = plot
    obj.person = person
    obj.frequency = frequency
    obj.is_active = is_active
    obj.last_run_date = last_run_date
    return obj


# ---------------------------------------------------------------------------
# GET /recurring-expenses/
# ---------------------------------------------------------------------------


def test_list_recurring_expenses_renders(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.list_recurring_expenses",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/recurring-expenses/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Recurrentes" in response.text


def test_list_recurring_expenses_with_msg(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.list_recurring_expenses",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/recurring-expenses/?msg=ok")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# GET /recurring-expenses/new
# ---------------------------------------------------------------------------


def test_new_recurring_expense_form_renders(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.list_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/recurring-expenses/new")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Nuevo Gasto Recurrente" in response.text


# ---------------------------------------------------------------------------
# POST /recurring-expenses/  (create)
# ---------------------------------------------------------------------------


def test_create_recurring_expense_redirects(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.create_recurring_expense_service",
        AsyncMock(return_value=_make_rec()),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            "/recurring-expenses/",
            data={
                "description": "Regadío Social",
                "amount": "50.0",
                "category": "Regadío Social",
                "frequency": "monthly",
                "person": "",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/recurring-expenses/" in response.headers["location"]


# ---------------------------------------------------------------------------
# GET /recurring-expenses/{id}/edit
# ---------------------------------------------------------------------------


def test_edit_recurring_expense_form_renders(monkeypatch) -> None:
    fake_db = _db()
    rec = _make_rec()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.get_recurring_expense",
        AsyncMock(return_value=rec),
    )
    monkeypatch.setattr(
        "app.routers.recurring_expenses.list_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/recurring-expenses/1/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Editar" in response.text


def test_edit_recurring_expense_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.get_recurring_expense",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.routers.recurring_expenses.list_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/recurring-expenses/99/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


# ---------------------------------------------------------------------------
# POST /recurring-expenses/{id}  (update)
# ---------------------------------------------------------------------------


def test_update_recurring_expense_redirects(monkeypatch) -> None:
    fake_db = _db()
    rec = _make_rec()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.get_recurring_expense",
        AsyncMock(return_value=rec),
    )
    monkeypatch.setattr(
        "app.routers.recurring_expenses.update_recurring_expense_service",
        AsyncMock(return_value=rec),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            "/recurring-expenses/1",
            data={
                "description": "Actualizado",
                "amount": "60.0",
                "frequency": "annual",
                "person": "",
                "is_active": "true",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/recurring-expenses/" in response.headers["location"]


def test_update_recurring_expense_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.get_recurring_expense",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            "/recurring-expenses/99",
            data={
                "description": "X",
                "amount": "1.0",
                "frequency": "monthly",
                "person": "",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


# ---------------------------------------------------------------------------
# POST /recurring-expenses/{id}/delete
# ---------------------------------------------------------------------------


def test_delete_recurring_expense_redirects(monkeypatch) -> None:
    fake_db = _db()
    rec = _make_rec()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.get_recurring_expense",
        AsyncMock(return_value=rec),
    )
    monkeypatch.setattr(
        "app.routers.recurring_expenses.delete_recurring_expense_service",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/recurring-expenses/1/delete")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/recurring-expenses/" in response.headers["location"]


def test_delete_recurring_expense_not_found_still_redirects(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.get_recurring_expense",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/recurring-expenses/99/delete")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


# ---------------------------------------------------------------------------
# POST /recurring-expenses/{id}/toggle
# ---------------------------------------------------------------------------


def test_toggle_recurring_expense_redirects(monkeypatch) -> None:
    fake_db = _db()
    rec = _make_rec(is_active=True)

    monkeypatch.setattr(
        "app.routers.recurring_expenses.get_recurring_expense",
        AsyncMock(return_value=rec),
    )
    monkeypatch.setattr(
        "app.routers.recurring_expenses.toggle_recurring_expense_service",
        AsyncMock(return_value=rec),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/recurring-expenses/1/toggle")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/recurring-expenses/" in response.headers["location"]


def test_toggle_recurring_expense_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()

    monkeypatch.setattr(
        "app.routers.recurring_expenses.get_recurring_expense",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/recurring-expenses/99/toggle")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303

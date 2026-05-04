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
    return MagicMock()


def test_incomes_list_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.incomes.get_incomes_list_context",
        AsyncMock(
            return_value={
                "incomes": [],
                "plots": [],
                "available_years": [],
                "selected_year": None,
                "totals": {},
            }
        ),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/incomes/?msg=ok")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Ingresos" in response.text


def test_new_income_form_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.incomes.list_plots", AsyncMock(return_value=[]))
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/incomes/new")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "/incomes/" in response.text


def test_create_income_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.incomes.create_income_service", AsyncMock())
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incomes/",
            data={
                "date": "2025-12-05",
                "amount_kg": "2.5",
                "category": "Extra",
                "euros_per_kg": "120",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Ingreso+registrado+correctamente" in response.headers["location"]


def test_edit_income_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.incomes.get_income", AsyncMock(return_value=None))
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/incomes/12/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Ingreso+no+encontrado" in response.headers["location"]


def test_edit_income_form_renders(monkeypatch) -> None:
    fake_db = _db()
    income = SimpleNamespace(
        id=12,
        date=datetime.date(2025, 12, 5),
        plot=None,
        plot_id=None,
        category="Extra",
        amount_kg=2.5,
        euros_per_kg=120.0,
        total=300.0,
    )
    monkeypatch.setattr(
        "app.routers.incomes.get_income", AsyncMock(return_value=income)
    )
    monkeypatch.setattr("app.routers.incomes.list_plots", AsyncMock(return_value=[]))
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/incomes/12/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Extra" in response.text


def test_update_income_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.incomes.get_income", AsyncMock(return_value=None))
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incomes/12",
            data={
                "date": "2025-12-05",
                "amount_kg": "2.5",
                "category": "Extra",
                "euros_per_kg": "120",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Ingreso+no+encontrado" in response.headers["location"]


def test_update_income_redirects(monkeypatch) -> None:
    fake_db = _db()
    obj = object()
    monkeypatch.setattr("app.routers.incomes.get_income", AsyncMock(return_value=obj))
    update_mock = AsyncMock()
    monkeypatch.setattr("app.routers.incomes.update_income_service", update_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incomes/12",
            data={
                "date": "2025-12-06",
                "amount_kg": "3",
                "category": "Primera",
                "euros_per_kg": "110",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Ingreso+actualizado+correctamente" in response.headers["location"]
    update_mock.assert_awaited_once()


def test_delete_income_redirects(monkeypatch) -> None:
    fake_db = _db()
    obj = object()
    monkeypatch.setattr("app.routers.incomes.get_income", AsyncMock(return_value=obj))
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.incomes.delete_income_service", delete_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/incomes/12/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Ingreso+eliminado+correctamente" in response.headers["location"]
    delete_mock.assert_awaited_once_with(fake_db, obj)


def test_delete_income_redirects_when_not_found(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.incomes.get_income", AsyncMock(return_value=None))
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.incomes.delete_income_service", delete_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/incomes/12/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Ingreso+eliminado+correctamente" in response.headers["location"]
    delete_mock.assert_not_called()

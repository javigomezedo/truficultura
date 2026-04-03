from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_user
from app.database import get_db
from app.main import app


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True)


def _db() -> MagicMock:
    return MagicMock()


def test_irrigation_list_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.irrigation.get_irrigation_list_context",
        AsyncMock(
            return_value={
                "records": [],
                "plots": [],
                "available_years": [],
                "count": 0,
                "selected_year": None,
                "selected_plot_id": None,
                "total_water_m3": 0,
            }
        ),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/irrigation/?msg=ok")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Riego" in response.text


def test_irrigation_new_form_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.services.irrigation_service._get_irrigable_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/irrigation/new")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "/irrigation/" in response.text


def test_irrigation_create_redirects(monkeypatch) -> None:
    fake_db = _db()
    create_mock = AsyncMock()
    monkeypatch.setattr("app.routers.irrigation.create_service", create_mock)
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/irrigation/",
            data={"plot_id": "1", "date": "2025-06-15", "water_m3": "10.5"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Riego+registrado+correctamente" in response.headers["location"]
    assert create_mock.await_count == 1


def test_irrigation_edit_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.irrigation.get_irrigation_record", AsyncMock(return_value=None)
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/irrigation/3/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Registro+no+encontrado" in response.headers["location"]


def test_irrigation_edit_form_renders(monkeypatch) -> None:
    fake_db = _db()
    record = SimpleNamespace(
        id=3,
        plot_id=1,
        date=datetime.date(2025, 6, 15),
        water_m3=10.5,
        expense_id=None,
        notes="nota",
    )
    expense = SimpleNamespace(
        id=9,
        description="Riego junio",
        date=datetime.date(2025, 6, 15),
        amount=42.5,
    )
    monkeypatch.setattr(
        "app.routers.irrigation.get_irrigation_record", AsyncMock(return_value=record)
    )
    monkeypatch.setattr(
        "app.services.irrigation_service._get_irrigable_plots",
        AsyncMock(return_value=[SimpleNamespace(id=1, name="Bancal Sur")]),
    )
    monkeypatch.setattr(
        "app.routers.irrigation.get_riego_expenses_for_plot",
        AsyncMock(return_value=[expense]),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/irrigation/3/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Riego junio" in response.text


def test_irrigation_update_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.irrigation.get_irrigation_record", AsyncMock(return_value=None)
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/irrigation/3/edit",
            data={"plot_id": "1", "date": "2025-06-15", "water_m3": "10.5"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Registro+no+encontrado" in response.headers["location"]


def test_irrigation_update_redirects(monkeypatch) -> None:
    fake_db = _db()
    record = SimpleNamespace(id=3)
    monkeypatch.setattr(
        "app.routers.irrigation.get_irrigation_record", AsyncMock(return_value=record)
    )
    update_mock = AsyncMock()
    monkeypatch.setattr("app.routers.irrigation.update_service", update_mock)
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/irrigation/3/edit",
            data={
                "plot_id": "1",
                "date": "2025-06-16",
                "water_m3": "11.0",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Riego+actualizado+correctamente" in response.headers["location"]
    update_mock.assert_awaited_once()


def test_irrigation_delete_redirects(monkeypatch) -> None:
    fake_db = _db()
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.irrigation.delete_service", delete_mock)
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/irrigation/3/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Riego+eliminado+correctamente" in response.headers["location"]
    delete_mock.assert_awaited_once_with(fake_db, 3, 1)


def test_irrigation_expenses_for_plot_returns_json(monkeypatch) -> None:
    fake_db = _db()
    expense = SimpleNamespace(
        id=9,
        description="Riego junio",
        date=SimpleNamespace(isoformat=lambda: "2025-06-15"),
        amount=42.5,
    )
    monkeypatch.setattr(
        "app.routers.irrigation.get_riego_expenses_for_plot",
        AsyncMock(return_value=[expense]),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/irrigation/expenses-for-plot/7")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {"id": 9, "description": "Riego junio", "date": "2025-06-15", "amount": 42.5}
    ]

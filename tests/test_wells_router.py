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


def test_wells_list_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.wells.get_wells_list_context",
        AsyncMock(
            return_value={
                "records": [],
                "plots": [],
                "years": [],
                "count": 0,
                "selected_year": None,
                "selected_plot": None,
                "total_wells_per_plant": 0,
                "total_estimated_wells": 0,
            }
        ),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/wells/?msg=ok")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Pozos" in response.text


def test_wells_new_form_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.services.wells_service._get_all_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/wells/new")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "/wells/" in response.text


def test_create_well_redirects(monkeypatch) -> None:
    fake_db = _db()
    create_mock = AsyncMock()
    monkeypatch.setattr("app.routers.wells.create_service", create_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/wells/",
            data={
                "plot_id": "1",
                "date": "2025-06-15",
                "wells_per_plant": "5",
                "expense_id": "",
                "notes": "Test",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Pozo+registrado+correctamente" in response.headers["location"]


def test_edit_well_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.wells.get_service", AsyncMock(return_value=None))
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/wells/5/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Registro+no+encontrado" in response.headers["location"]


def test_edit_well_form_renders(monkeypatch) -> None:
    fake_db = _db()
    well = SimpleNamespace(
        id=5,
        plot_id=1,
        date=datetime.date(2025, 6, 15),
        wells_per_plant=5,
        expense_id=None,
        notes="Test",
        plot=SimpleNamespace(name="Plot1", num_plants=100),
    )
    monkeypatch.setattr("app.routers.wells.get_service", AsyncMock(return_value=well))
    monkeypatch.setattr(
        "app.services.wells_service._get_all_plots",
        AsyncMock(return_value=[SimpleNamespace(id=1, name="Plot1", num_plants=100)]),
    )
    monkeypatch.setattr(
        "app.routers.wells.get_well_expenses_for_plot",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/wells/5/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Plot1" in response.text


def test_update_well_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.wells.get_service", AsyncMock(return_value=None))
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/wells/5/edit",
            data={
                "plot_id": "1",
                "date": "2025-06-15",
                "wells_per_plant": "5",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Registro+no+encontrado" in response.headers["location"]


def test_update_well_redirects(monkeypatch) -> None:
    fake_db = _db()
    well = object()
    monkeypatch.setattr("app.routers.wells.get_service", AsyncMock(return_value=well))
    update_mock = AsyncMock()
    monkeypatch.setattr("app.routers.wells.update_service", update_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/wells/5/edit",
            data={
                "plot_id": "1",
                "date": "2025-06-15",
                "wells_per_plant": "5",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Pozo+actualizado+correctamente" in response.headers["location"]


def test_delete_well_redirects(monkeypatch) -> None:
    fake_db = _db()
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.wells.delete_service", delete_mock)
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/wells/5/delete",
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Pozo+eliminado+correctamente" in response.headers["location"]


def test_expenses_for_plot_json(monkeypatch) -> None:
    fake_db = _db()
    expenses = [
        SimpleNamespace(
            id=1,
            description="Gasto pozos",
            category="Pozos",
            amount=100.0,
            date=datetime.date(2025, 6, 15),
        )
    ]
    monkeypatch.setattr(
        "app.routers.wells.get_well_expenses_for_plot",
        AsyncMock(return_value=expenses),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/wells/expenses-for-plot/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == 1

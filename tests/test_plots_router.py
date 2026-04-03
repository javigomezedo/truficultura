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


def test_plots_list_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plots.list_plots_service", AsyncMock(return_value=[])
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plots/?msg=ok")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Parcel" in response.text


def test_new_plot_form_renders() -> None:
    app.dependency_overrides[require_user] = _user
    try:
        client = TestClient(app)
        response = client.get("/plots/new")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "/plots/" in response.text


def test_create_plot_redirects_and_maps_irrigation(monkeypatch) -> None:
    fake_db = _db()
    create_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plots.create_plot_service", create_mock)
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/plots/",
            data={
                "name": "Bancal Sur",
                "planting_date": "2020-03-15",
                "num_plants": "100",
                "has_irrigation": "true",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Parcela+creada+correctamente" in response.headers["location"]
    assert create_mock.await_args.kwargs["has_irrigation"] is True


def test_edit_plot_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.plots.get_plot", AsyncMock(return_value=None))
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plots/5/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Parcela+no+encontrada" in response.headers["location"]


def test_edit_plot_form_renders(monkeypatch) -> None:
    fake_db = _db()
    plot = SimpleNamespace(
        id=5,
        name="Bancal Sur",
        sector="A1",
        polygon="5",
        plot_num="120",
        cadastral_ref="44223A021001200000FP",
        hydrant="H-03",
        num_plants=100,
        area_ha=1.5,
        percentage=50.0,
        planting_date=datetime.date(2020, 3, 15),
        production_start=datetime.date(2024, 11, 1),
        has_irrigation=True,
    )
    monkeypatch.setattr("app.routers.plots.get_plot", AsyncMock(return_value=plot))
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plots/5/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Bancal Sur" in response.text


def test_update_plot_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.plots.get_plot", AsyncMock(return_value=None))
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/plots/5",
            data={
                "name": "Bancal Sur",
                "planting_date": "2020-03-15",
                "num_plants": "100",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Parcela+no+encontrada" in response.headers["location"]


def test_update_plot_redirects_and_maps_irrigation_false(monkeypatch) -> None:
    fake_db = _db()
    plot = object()
    monkeypatch.setattr("app.routers.plots.get_plot", AsyncMock(return_value=plot))
    update_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plots.update_plot_service", update_mock)
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/plots/5",
            data={
                "name": "Bancal Norte",
                "planting_date": "2020-03-15",
                "num_plants": "100",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Parcela+actualizada+correctamente" in response.headers["location"]
    assert update_mock.await_args.kwargs["has_irrigation"] is False


def test_delete_plot_redirects(monkeypatch) -> None:
    fake_db = _db()
    obj = object()
    monkeypatch.setattr("app.routers.plots.get_plot", AsyncMock(return_value=obj))
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plots.delete_plot_service", delete_mock)
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/plots/5/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Parcela+eliminada+correctamente" in response.headers["location"]
    delete_mock.assert_awaited_once_with(fake_db, obj)


def test_delete_plot_redirects_when_not_found(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr("app.routers.plots.get_plot", AsyncMock(return_value=None))
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plots.delete_plot_service", delete_mock)
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/plots/5/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Parcela+eliminada+correctamente" in response.headers["location"]
    delete_mock.assert_not_called()

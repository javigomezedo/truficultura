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


def _plot(plot_id: int = 10) -> SimpleNamespace:
    return SimpleNamespace(id=plot_id, name="Parcela Norte")


def test_map_view_renders(monkeypatch) -> None:
    db = _db()
    monkeypatch.setattr("app.routers.plants.get_plot", AsyncMock(return_value=_plot()))
    monkeypatch.setattr(
        "app.routers.plants.plants_service.get_plot_map_context",
        AsyncMock(
            return_value={"rows": [], "selected_campaign": 2025, "has_plants": False}
        ),
    )
    monkeypatch.setattr(
        "app.routers.plants.plants_service.has_active_truffle_events",
        AsyncMock(return_value=False),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/plots/10/map?campaign=2025")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Mapa de plantas" in response.text


def test_configure_map_submit_redirects_on_invalid_format(monkeypatch) -> None:
    db = _db()
    monkeypatch.setattr("app.routers.plants.get_plot", AsyncMock(return_value=_plot()))

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/plots/10/map/configure",
            data={"row_config": "4,a,3"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Formato+incorrecto" in response.headers["location"]


def test_configure_map_submit_calls_service(monkeypatch) -> None:
    db = _db()
    plot = _plot()
    monkeypatch.setattr("app.routers.plants.get_plot", AsyncMock(return_value=plot))
    configure_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.routers.plants.plants_service.configure_plot_map",
        configure_mock,
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/plots/10/map/configure",
            data={"row_config": "4,5,3"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Mapa+configurado+correctamente" in response.headers["location"]
    assert configure_mock.await_args.kwargs["row_counts"] == [4, 5, 3]


def test_add_truffle_event_redirects_with_campaign(monkeypatch) -> None:
    db = _db()
    plant = SimpleNamespace(id=3, plot_id=10)
    monkeypatch.setattr(
        "app.routers.plants.plants_service.get_plant",
        AsyncMock(return_value=plant),
    )
    create_mock = AsyncMock(return_value=SimpleNamespace(id=1))
    monkeypatch.setattr(
        "app.routers.plants.truffle_events_service.create_event",
        create_mock,
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/plots/10/plants/3/add",
            data={"campaign": "2025"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "campaign=2025" in response.headers["location"]
    create_mock.assert_awaited_once()


def test_undo_truffle_event_redirects_when_no_event(monkeypatch) -> None:
    db = _db()
    plant = SimpleNamespace(id=3, plot_id=10)
    monkeypatch.setattr(
        "app.routers.plants.plants_service.get_plant",
        AsyncMock(return_value=plant),
    )
    monkeypatch.setattr(
        "app.routers.plants.truffle_events_service.undo_last_event",
        AsyncMock(return_value=None),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/plots/10/plants/3/undo", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "No+hay+registro+para+deshacer" in response.headers["location"]


def test_list_truffle_events_renders(monkeypatch) -> None:
    db = _db()
    monkeypatch.setattr(
        "app.routers.plants.list_plots", AsyncMock(return_value=[_plot()])
    )
    monkeypatch.setattr(
        "app.routers.plants.truffle_events_service.list_events",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=1,
                    created_at=datetime.datetime(2026, 4, 8, 10, 30, 0),
                    plot_id=10,
                    plant_id=3,
                    source="manual",
                )
            ]
        ),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/truffles/?camp=2025&plot_id=10&plant_id=3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Eventos de trufas" in response.text

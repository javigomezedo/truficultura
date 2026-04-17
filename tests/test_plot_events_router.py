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


def test_plot_events_list_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_events",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.routers.plot_events._get_all_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/list?msg=ok")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Eventos de Parcela" in response.text


def test_plot_events_list_accepts_empty_query_ints(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_events",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.routers.plot_events._get_all_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/list?plot_id=&campaign=&event_type=poda")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_plot_events_list_shows_links_for_linked_records(monkeypatch) -> None:
    fake_db = _db()
    linked_irrigation = SimpleNamespace(
        id=1,
        plot_id=2,
        plot=SimpleNamespace(name="Parcela 1"),
        event_type="riego",
        date=datetime.date(2025, 6, 15),
        notes="auto",
        related_irrigation_id=10,
        related_well_id=None,
    )
    linked_well = SimpleNamespace(
        id=2,
        plot_id=2,
        plot=SimpleNamespace(name="Parcela 1"),
        event_type="pozo",
        date=datetime.date(2025, 6, 16),
        notes="auto",
        related_irrigation_id=None,
        related_well_id=20,
    )
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_events",
        AsyncMock(return_value=[linked_irrigation, linked_well]),
    )
    monkeypatch.setattr(
        "app.routers.plot_events._get_all_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/list")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "/irrigation/10/edit" in response.text
    assert "/wells/20/edit" in response.text


def test_plot_events_root_redirects_to_calendar(monkeypatch) -> None:
    fake_db = _db()
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/plot-events/calendar-view"


def test_plot_events_json_returns_data(monkeypatch) -> None:
    fake_db = _db()
    record = SimpleNamespace(
        id=1,
        plot_id=2,
        event_type="labrado",
        date=datetime.date(2025, 6, 15),
        notes="ok",
        is_recurring=True,
        related_irrigation_id=None,
        related_well_id=None,
    )
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_events",
        AsyncMock(return_value=[record]),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/json/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": 1,
            "plot_id": 2,
            "event_type": "labrado",
            "date": "2025-06-15",
            "notes": "ok",
            "is_recurring": True,
            "related_irrigation_id": None,
            "related_well_id": None,
        }
    ]


def test_plot_events_create_redirects(monkeypatch) -> None:
    fake_db = _db()
    create_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plot_events.create_plot_event", create_mock)
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/plot-events/",
            data={
                "plot_id": "1",
                "event_type": "labrado",
                "date": "2025-06-15",
                "notes": "ok",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Evento+registrado+correctamente" in response.headers["location"]
    assert create_mock.await_count == 1


def test_plot_events_edit_not_found_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_event", AsyncMock(return_value=None)
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/5/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Evento+no+encontrado" in response.headers["location"]


def test_plot_events_edit_form_renders(monkeypatch) -> None:
    fake_db = _db()
    record = SimpleNamespace(
        id=5,
        plot_id=1,
        event_type="poda",
        date=datetime.date(2025, 6, 15),
        notes="Test",
    )
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_event", AsyncMock(return_value=record)
    )
    monkeypatch.setattr(
        "app.routers.plot_events._get_all_plots",
        AsyncMock(return_value=[SimpleNamespace(id=1, name="Plot1")]),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/5/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Editar evento" in response.text


def test_plot_events_edit_linked_redirects(monkeypatch) -> None:
    fake_db = _db()
    record = SimpleNamespace(
        id=5,
        plot_id=1,
        event_type="riego",
        date=datetime.date(2025, 6, 15),
        notes="auto",
        related_irrigation_id=10,
        related_well_id=None,
    )
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_event", AsyncMock(return_value=record)
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/5/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "no+se+puede+editar+desde+aqu%C3%AD" in response.headers["location"]


def test_plot_events_update_redirects(monkeypatch) -> None:
    fake_db = _db()
    record = SimpleNamespace(id=5, user_id=1, plot_id=1, event_type="poda")
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_event", AsyncMock(return_value=record)
    )
    update_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plot_events.update_plot_event", update_mock)

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/plot-events/5/edit",
            data={"event_type": "poda", "date": "2025-06-20", "notes": "ok"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Evento+actualizado+correctamente" in response.headers["location"]
    update_mock.assert_awaited_once()


def test_plot_events_update_linked_redirects(monkeypatch) -> None:
    fake_db = _db()
    record = SimpleNamespace(
        id=5,
        user_id=1,
        plot_id=1,
        event_type="riego",
        related_irrigation_id=10,
        related_well_id=None,
    )
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_event", AsyncMock(return_value=record)
    )
    update_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plot_events.update_plot_event", update_mock)

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/plot-events/5/edit",
            data={"event_type": "poda", "date": "2025-06-20", "notes": "ok"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "no+se+puede+editar+desde+aqu%C3%AD" in response.headers["location"]
    update_mock.assert_not_awaited()


def test_plot_events_delete_redirects(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_event", AsyncMock(return_value=None)
    )
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plot_events.delete_plot_event", delete_mock)

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/plot-events/5/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "Evento+eliminado+correctamente" in response.headers["location"]
    delete_mock.assert_awaited_once_with(fake_db, 5, 1)


def test_plot_events_delete_linked_redirects(monkeypatch) -> None:
    fake_db = _db()
    record = SimpleNamespace(
        id=5,
        related_irrigation_id=10,
        related_well_id=None,
    )
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_event", AsyncMock(return_value=record)
    )
    delete_mock = AsyncMock()
    monkeypatch.setattr("app.routers.plot_events.delete_plot_event", delete_mock)

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post("/plot-events/5/delete", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "no+se+puede+eliminar+desde+aqu%C3%AD" in response.headers["location"]
    delete_mock.assert_not_awaited()


def test_plot_events_calendar_json(monkeypatch) -> None:
    fake_db = _db()
    records = [
        SimpleNamespace(
            id=1,
            plot_id=1,
            event_type="poda",
            date=datetime.date(2025, 6, 20),
            notes="a",
            related_irrigation_id=None,
            related_well_id=None,
        )
    ]
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_events", AsyncMock(return_value=records)
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/calendar/?year=2025&month=6")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    assert "2025-06-20" in payload["days"]


def test_plot_events_calendar_json_accepts_empty_plot_id(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_events", AsyncMock(return_value=[])
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/calendar/?plot_id=")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_plot_events_calendar_view_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_events.get_plot_events", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        "app.routers.plot_events._get_all_plots", AsyncMock(return_value=[])
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-events/calendar-view?year=2025&month=6")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Calendario de eventos" in response.text

from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_subscription
from app.database import get_db
from app.main import app
from app.plan_access import require_write_access


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True, active_tenant_id=1)


def _db() -> MagicMock:
    return MagicMock()


def _list_ctx():
    return {
        "records": [],
        "plots": [],
        "years": [],
        "count": 0,
        "selected_year": None,
        "selected_plot": None,
        "selected_source": None,
        "selected_municipio_cod": None,
        "only_with_rain": False,
        "total_precipitation": 0.0,
        "sort_by": "date",
        "sort_order": "desc",
        "municipios": [],
    }


def _calendar_ctx():
    return {
        "months": [],
        "day_labels": [],
        "total_mm": 0.0,
        "total_m3": None,
        "area_ha": None,
        "rain_days": 0,
        "selected_year": 2025,
        "selected_plot": None,
        "selected_municipio": None,
        "selected_source": None,
        "plots": [],
        "years": [],
        "municipios": [],
        "municipio_cod_to_name": {},
    }


def test_lluvia_list_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.lluvia.get_rainfall_list_context",
        AsyncMock(return_value=_list_ctx()),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/lluvia/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_lluvia_nuevo_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.lluvia._get_user_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/lluvia/nuevo")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_lluvia_create_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.lluvia.create_rainfall_record",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[require_write_access] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            "/lluvia/",
            data={
                "plot_id": "1",
                "municipio_cod": "",
                "date": "2025-11-01",
                "precipitation_mm": "5.2",
                "source": "manual",
                "notes": "",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/lluvia/" in response.headers["location"]


def test_lluvia_edit_form_renders(monkeypatch) -> None:
    record = SimpleNamespace(
        id=1,
        tenant_id=1,
        plot_id=1,
        date=datetime.date(2025, 11, 1),
        precipitation_mm=5.0,
        source="manual",
        notes=None,
        created_by_user_id=1,
        municipio_cod=None,
    )
    monkeypatch.setattr(
        "app.routers.lluvia.get_rainfall_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.routers.lluvia._get_user_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/lluvia/1/editar")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_lluvia_edit_form_not_found_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.lluvia.get_rainfall_record",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/lluvia/99/editar")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


def test_lluvia_edit_aemet_record_redirects(monkeypatch) -> None:
    """AEMET records (created_by_user_id=None) can't be edited."""
    record = SimpleNamespace(
        id=1,
        tenant_id=1,
        plot_id=None,
        date=datetime.date(2025, 11, 1),
        precipitation_mm=5.0,
        source="aemet",
        notes=None,
        created_by_user_id=None,  # AEMET record
        municipio_cod="22125",
    )
    monkeypatch.setattr(
        "app.routers.lluvia.get_rainfall_record",
        AsyncMock(return_value=record),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/lluvia/1/editar")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


def test_lluvia_update_redirects(monkeypatch) -> None:
    record = SimpleNamespace(
        id=1,
        tenant_id=1,
        plot_id=1,
        date=datetime.date(2025, 11, 1),
        precipitation_mm=5.0,
        source="manual",
        notes=None,
        created_by_user_id=1,
        municipio_cod=None,
    )
    monkeypatch.setattr(
        "app.routers.lluvia.get_rainfall_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.routers.lluvia.update_rainfall_record",
        AsyncMock(return_value=record),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[require_write_access] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            "/lluvia/1/editar",
            data={
                "plot_id": "1",
                "municipio_cod": "",
                "date": "2025-11-01",
                "precipitation_mm": "6.0",
                "source": "manual",
                "notes": "",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/lluvia/" in response.headers["location"]


def test_lluvia_delete_redirects(monkeypatch) -> None:
    record = SimpleNamespace(
        id=1,
        tenant_id=1,
        plot_id=1,
        date=datetime.date(2025, 11, 1),
        precipitation_mm=5.0,
        source="manual",
        notes=None,
        created_by_user_id=1,
        municipio_cod=None,
    )
    monkeypatch.setattr(
        "app.routers.lluvia.get_rainfall_record",
        AsyncMock(return_value=record),
    )
    monkeypatch.setattr(
        "app.routers.lluvia.delete_rainfall_record",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[require_write_access] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/lluvia/1/eliminar")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/lluvia/" in response.headers["location"]


def test_lluvia_calendario_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.lluvia.get_rainfall_calendar_context",
        AsyncMock(return_value=_calendar_ctx()),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/lluvia/calendario")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

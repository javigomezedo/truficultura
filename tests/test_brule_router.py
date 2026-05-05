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
    return SimpleNamespace(
        id=1,
        role="user",
        is_active=True,
        active_tenant_id=1,
    )


def _db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalars=MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))))
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.delete = AsyncMock()
    return db


def _fake_plot(plot_id: int = 2) -> SimpleNamespace:
    return SimpleNamespace(id=plot_id, name="Parcela A", tenant_id=1)


def _fake_plant(plant_id: int = 5, plot_id: int = 2) -> SimpleNamespace:
    return SimpleNamespace(id=plant_id, plot_id=plot_id, label="P1", tenant_id=1)


def _fake_record(record_id: int = 99) -> SimpleNamespace:
    return SimpleNamespace(
        id=record_id,
        tenant_id=1,
        plant_id=5,
        plot_id=2,
        diameter_cm=45,
        record_date=datetime.date(2025, 11, 5),
        plant=_fake_plant(),
        plot=_fake_plot(),
    )


# ─────────────────────────────────────────────────────────────────────────────
# GET /brule/ — global list
# ─────────────────────────────────────────────────────────────────────────────


def test_brule_list_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.brule.brule_service.list_brule_records",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.routers.brule.list_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/brule/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Brul" in response.text


def test_brule_list_with_records(monkeypatch) -> None:
    records = [_fake_record(record_id=1), _fake_record(record_id=2)]
    monkeypatch.setattr(
        "app.routers.brule.brule_service.list_brule_records",
        AsyncMock(return_value=records),
    )
    monkeypatch.setattr(
        "app.routers.brule.list_plots",
        AsyncMock(return_value=[_fake_plot()]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/brule/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# GET /brule/correlacion
# ─────────────────────────────────────────────────────────────────────────────


def test_brule_correlacion_renders_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.brule.brule_service.get_brule_production_correlation",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.routers.brule.list_plots",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/brule/correlacion")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "correlaci" in response.text.lower()


def test_brule_correlacion_with_data(monkeypatch) -> None:
    correlation = [
        {"plant_label": "P1", "last_diameter_cm": 55, "total_weight_kg": 1.2},
        {"plant_label": "P2", "last_diameter_cm": 30, "total_weight_kg": 0.4},
    ]
    monkeypatch.setattr(
        "app.routers.brule.brule_service.get_brule_production_correlation",
        AsyncMock(return_value=correlation),
    )
    monkeypatch.setattr(
        "app.routers.brule.list_plots",
        AsyncMock(return_value=[_fake_plot()]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/brule/correlacion")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "P1" in response.text


# ─────────────────────────────────────────────────────────────────────────────
# GET /plots/{plot_id}/plants/{plant_id}/brule/
# ─────────────────────────────────────────────────────────────────────────────


def test_plant_brule_view_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.brule.get_plot",
        AsyncMock(return_value=_fake_plot(plot_id=2)),
    )
    monkeypatch.setattr(
        "app.routers.brule.get_plant",
        AsyncMock(return_value=_fake_plant(plant_id=5, plot_id=2)),
    )
    monkeypatch.setattr(
        "app.routers.brule.brule_service.get_brule_evolution",
        AsyncMock(return_value=[(datetime.date(2025, 6, 1), 45)]),
    )
    monkeypatch.setattr(
        "app.routers.brule.brule_service.list_brule_records",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/plots/2/plants/5/brule/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_plant_brule_view_plot_not_found_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.brule.get_plot",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/plots/999/plants/5/brule/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/plots/" in response.headers["location"]


def test_plant_brule_view_plant_not_found_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.brule.get_plot",
        AsyncMock(return_value=_fake_plot(plot_id=2)),
    )
    monkeypatch.setattr(
        "app.routers.brule.get_plant",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.get("/plots/2/plants/5/brule/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/map" in response.headers["location"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /plots/{plot_id}/plants/{plant_id}/brule/
# ─────────────────────────────────────────────────────────────────────────────


def test_plant_brule_create_redirects_on_success(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.brule.get_plot",
        AsyncMock(return_value=_fake_plot(plot_id=2)),
    )
    monkeypatch.setattr(
        "app.routers.brule.brule_service.create_brule_record",
        AsyncMock(return_value=_fake_record()),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[require_write_access] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            "/plots/2/plants/5/brule/",
            data={"record_date": "2025-11-05", "diameter_cm": "50"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/plots/2/plants/5/brule/" in response.headers["location"]


def test_plant_brule_create_invalid_date_redirects(monkeypatch) -> None:
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[require_write_access] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            "/plots/2/plants/5/brule/",
            data={"record_date": "not-a-date", "diameter_cm": "50"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "msg=" in response.headers["location"]


# ─────────────────────────────────────────────────────────────────────────────
# POST /brule/{record_id}/delete
# ─────────────────────────────────────────────────────────────────────────────


def test_brule_delete_redirects(monkeypatch) -> None:
    rec = _fake_record(record_id=99)
    monkeypatch.setattr(
        "app.routers.brule.brule_service.get_brule_record",
        AsyncMock(return_value=rec),
    )
    monkeypatch.setattr(
        "app.routers.brule.brule_service.delete_brule_record",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[require_write_access] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/brule/99/delete")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


def test_brule_delete_not_found_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.brule.brule_service.get_brule_record",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[require_write_access] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/brule/999/delete")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303

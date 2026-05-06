from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_user
from app.database import get_db
from app.main import app


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True, active_tenant_id=1)


def _db() -> MagicMock:
    db = MagicMock()
    db.commit = AsyncMock()
    return db


def test_unread_count_returns_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.get_unread_count",
        AsyncMock(return_value=3),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/notifications/unread-count")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"count": 3}


def test_notifications_list_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.list_notifications",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.routers.notifications.get_unread_count",
        AsyncMock(return_value=0),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/notifications/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Avisos" in response.text


def test_mark_read_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.mark_read",
        AsyncMock(return_value=True),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/notifications/1/read")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/notifications/"


def test_mark_all_read_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.mark_all_read",
        AsyncMock(return_value=5),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/notifications/read-all")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/notifications/" in response.headers["location"]


def test_dismiss_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.dismiss",
        AsyncMock(return_value=True),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post("/notifications/1/dismiss")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/notifications/"


def test_preferences_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.notifications.get_preferences",
        AsyncMock(
            return_value={
                ntype: {
                    "enabled": True,
                    "email_enabled": False,
                    "threshold_days": None,
                    "threshold_value": None,
                }
                for ntype in [
                    "campaign_start",
                    "no_truffle_events",
                    "low_water_balance",
                    "user_inactive",
                    "no_rainfall_data",
                    "campaign_end_reminder",
                    "stressed_plant_no_replacement",
                    "no_irrigation_summer",
                    "no_brule_measurement",
                    "low_harvest_vs_previous",
                ]
            }
        ),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/notifications/preferences")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Preferencias" in response.text

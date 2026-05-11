from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_subscription
from app.database import get_db
from app.main import app


def _user() -> SimpleNamespace:
    # No active_tenant → plan_access returns "trial" → all features available
    return SimpleNamespace(id=1, role="user", is_active=True, active_tenant_id=1)


def _db() -> MagicMock:
    return MagicMock()


def test_weather_page_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.weather.get_weather_contexts",
        AsyncMock(
            return_value=[
                {
                    "available": True,
                    "display_name": "Huesca",
                    "source": "aemet",
                    "temperature": 18.5,
                    "humidity": 60.0,
                    "precipitation_today": 0.0,
                    "rain_month": 12.0,
                    "wind_speed": None,
                    "updated_ago_label": "hace 5 min",
                    "freshness": "fresh",
                    "tomorrow_sky": "Despejado",
                    "tomorrow_t_max": 22.0,
                    "tomorrow_t_min": 10.0,
                    "tomorrow_prob_prec": 5,
                }
            ]
        ),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/tiempo/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_weather_widget_returns_json(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.weather.get_weather_contexts",
        AsyncMock(
            return_value=[
                {
                    "available": True,
                    "display_name": "Huesca",
                    "source": "aemet",
                    "temperature": 18.5,
                    "humidity": 60.0,
                    "precipitation_today": 0.2,
                    "rain_month": 8.0,
                    "updated_ago_label": "hace 2 min",
                    "freshness": "fresh",
                    "tomorrow_sky": "Nuboso",
                    "tomorrow_t_max": 20.0,
                    "tomorrow_t_min": 9.0,
                    "tomorrow_prob_prec": 30,
                }
            ]
        ),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/tiempo/widget")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert len(data["municipios"]) == 1
    assert data["municipios"][0]["display_name"] == "Huesca"


def test_weather_widget_returns_unavailable_when_no_municipio(monkeypatch) -> None:
    """Single error context triggers the unavailable short-circuit."""
    monkeypatch.setattr(
        "app.routers.weather.get_weather_contexts",
        AsyncMock(
            return_value=[
                {
                    "available": False,
                    "error": "no_municipio",
                }
            ]
        ),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/tiempo/widget")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is False
    assert data["error"] == "no_municipio"


def test_weather_widget_skips_unavailable_contexts(monkeypatch) -> None:
    """Multiple contexts: unavailable ones are skipped, available ones are returned."""
    monkeypatch.setattr(
        "app.routers.weather.get_weather_contexts",
        AsyncMock(
            return_value=[
                {"available": False, "error": "api_error"},
                {
                    "available": True,
                    "display_name": "Teruel",
                    "source": "aemet",
                    "temperature": 15.0,
                    "humidity": 55.0,
                    "precipitation_today": 0.0,
                    "rain_month": 5.0,
                    "updated_ago_label": "hace 1 min",
                    "freshness": "fresh",
                    "tomorrow_sky": "Despejado",
                    "tomorrow_t_max": 18.0,
                    "tomorrow_t_min": 7.0,
                    "tomorrow_prob_prec": 0,
                },
            ]
        ),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/tiempo/widget")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert len(data["municipios"]) == 1
    assert data["municipios"][0]["display_name"] == "Teruel"

from __future__ import annotations

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


def test_maps_index_renders_plot_cards(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.maps.list_plots",
        AsyncMock(
            return_value=[
                SimpleNamespace(
                    id=10,
                    name="Parcela Norte",
                    polygon=1,
                    plot_num=5,
                    num_plants=30,
                    area_ha=1.5,
                ),
                SimpleNamespace(
                    id=11,
                    name="Parcela Sur",
                    polygon=2,
                    plot_num=6,
                    num_plants=20,
                    area_ha=None,
                ),
            ]
        ),
    )

    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/maps/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Parcela Norte" in response.text
    assert "Parcela Sur" in response.text
    assert "/plots/10/map" in response.text
    assert "/plots/11/map" in response.text


def test_maps_index_empty_state(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.maps.list_plots",
        AsyncMock(return_value=[]),
    )

    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/maps/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Nueva parcela" in response.text

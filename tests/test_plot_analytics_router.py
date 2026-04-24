from __future__ import annotations

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


def test_plot_analytics_overview_renders(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_campaign_dataset",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_irrigation_vs_production_analysis",
        AsyncMock(
            return_value={
                "sample_size": 0,
                "avg_water_m3": 0.0,
                "avg_production_kg": 0.0,
                "water_bands": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_pruning_vs_production_analysis",
        AsyncMock(
            return_value={
                "sample_size": 0,
                "with_pruning_count": 0,
                "without_pruning_count": 0,
                "avg_production_with_pruning": 0.0,
                "avg_production_without_pruning": 0.0,
                "delta_percent": None,
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_tilling_vs_production_analysis",
        AsyncMock(
            return_value={
                "sample_size": 0,
                "groups": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.detect_irrigation_thresholds",
        AsyncMock(
            return_value={
                "sample_size": 0,
                "status": "insufficient_data",
                "plateau_start_m3": None,
                "water_bands": [],
                "marginal_gains": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_all_plot_thresholds",
        AsyncMock(return_value=[]),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Análisis de rendimiento" in response.text
    assert "Interpretación en lenguaje sencillo" in response.text


def test_plot_analytics_dataset_json(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_campaign_dataset",
        AsyncMock(return_value=[{"campaign_year": 2025, "plot_name": "Parcela A"}]),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/dataset")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == [{"campaign_year": 2025, "plot_name": "Parcela A"}]


def test_plot_analytics_irrigation_impact_json(monkeypatch) -> None:
    fake_db = _db()
    payload = {
        "sample_size": 3,
        "avg_water_m3": 12.5,
        "avg_production_kg": 60.0,
        "water_bands": [{"band": "bajo", "count": 1, "avg_production_kg": 50.0}],
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_irrigation_vs_production_analysis",
        AsyncMock(return_value=payload),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/irrigation-impact")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == payload


def test_plot_analytics_comparison_view_renders(monkeypatch) -> None:
    fake_db = _db()
    comparison_payload = {
        "sample_size": 2,
        "plots_included": 2,
        "points": [
            {
                "x": 10.0,
                "y": 40.0,
                "plot_name": "Parcela A",
                "plot_id": 1,
                "campaign_year": 2025,
                "kg_per_m3": 4.0,
            },
            {
                "x": 20.0,
                "y": 30.0,
                "plot_name": "Parcela B",
                "plot_id": 2,
                "campaign_year": 2025,
                "kg_per_m3": 1.5,
            },
        ],
        "efficiency_ranking": [
            {
                "plot_id": 1,
                "plot_name": "Parcela A",
                "sample_size": 1,
                "total_production_kg": 40.0,
                "total_water_m3": 10.0,
                "kg_per_m3": 4.0,
            },
            {
                "plot_id": 2,
                "plot_name": "Parcela B",
                "sample_size": 1,
                "total_production_kg": 30.0,
                "total_water_m3": 20.0,
                "kg_per_m3": 1.5,
            },
        ],
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_multi_plot_comparison",
        AsyncMock(return_value=comparison_payload),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_campaign_dataset",
        AsyncMock(return_value=[{"campaign_year": 2025}]),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/comparison-view")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Parcela A" in response.text
    assert "Parcela B" in response.text


def test_plot_analytics_comparison_view_accepts_empty_campaign_from(
    monkeypatch,
) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_multi_plot_comparison",
        AsyncMock(
            return_value={
                "sample_size": 0,
                "plots_included": 0,
                "points": [],
                "efficiency_ranking": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_campaign_dataset",
        AsyncMock(return_value=[]),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get(
            "/plot-analytics/comparison-view?campaign_from=&campaign_to=2017"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_plot_analytics_comparison_view_empty(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_multi_plot_comparison",
        AsyncMock(
            return_value={
                "sample_size": 0,
                "plots_included": 0,
                "points": [],
                "efficiency_ranking": [],
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_campaign_dataset",
        AsyncMock(return_value=[]),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/comparison-view")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "No hay datos suficientes" in response.text
    fake_db = _db()
    payload = {
        "sample_size": 3,
        "with_pruning_count": 2,
        "without_pruning_count": 1,
        "avg_production_with_pruning": 70.0,
        "avg_production_without_pruning": 55.0,
        "delta_percent": 27.27,
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_pruning_vs_production_analysis",
        AsyncMock(return_value=payload),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/pruning-impact")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == payload


def test_plot_analytics_management_impact_json(monkeypatch) -> None:
    fake_db = _db()
    payload = {
        "sample_size": 4,
        "groups": [{"group": "solo_labrado", "count": 2, "avg_production_kg": 61.2}],
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_tilling_vs_production_analysis",
        AsyncMock(return_value=payload),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/management-impact")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == payload


def test_plot_analytics_irrigation_thresholds_json(monkeypatch) -> None:
    fake_db = _db()
    payload = {
        "sample_size": 5,
        "status": "ok",
        "plateau_start_m3": 32.0,
        "water_bands": [],
        "marginal_gains": [],
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.detect_irrigation_thresholds",
        AsyncMock(return_value=payload),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/irrigation-thresholds")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == payload


def test_plot_analytics_plot_detail_renders(monkeypatch) -> None:
    fake_db = _db()
    payload = {
        "plot": SimpleNamespace(id=1, name="Parcela A"),
        "dataset": [{"campaign_year": 2025, "total_production_kg": 50.0}],
        "labels": [2025],
        "production_series": [50.0],
        "water_series": [10.0],
        "pruning_series": [1],
        "tilling_series": [0],
        "digging_series": [0],
        "scatter_points": [{"x": 10.0, "y": 50.0, "campaign_year": 2025}],
    }
    _threshold_empty = {
        "sample_size": 0,
        "status": "insufficient_data",
        "plateau_start_m3": None,
        "water_bands": [],
        "marginal_gains": [],
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_plot_detail_context",
        AsyncMock(return_value=payload),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.detect_irrigation_thresholds",
        AsyncMock(side_effect=[_threshold_empty, _threshold_empty]),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/plot/1")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Parcela A" in response.text


def test_plot_analytics_plot_detail_not_found(monkeypatch) -> None:
    fake_db = _db()
    _threshold_empty = {
        "sample_size": 0,
        "status": "insufficient_data",
        "plateau_start_m3": None,
        "water_bands": [],
        "marginal_gains": [],
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_plot_detail_context",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "app.routers.plot_analytics.detect_irrigation_thresholds",
        AsyncMock(side_effect=[_threshold_empty, _threshold_empty]),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/plot/999")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert "Parcela no encontrada" in response.text


def test_plot_analytics_plot_detail_json(monkeypatch) -> None:
    fake_db = _db()
    payload = {
        "plot": SimpleNamespace(id=1, name="Parcela A"),
        "dataset": [{"campaign_year": 2025, "total_production_kg": 50.0}],
        "labels": [2025],
        "production_series": [50.0],
        "water_series": [10.0],
        "pruning_series": [1],
        "tilling_series": [0],
        "digging_series": [0],
        "scatter_points": [{"x": 10.0, "y": 50.0, "campaign_year": 2025}],
        "insights": {"status": "ok", "messages": ["msg"]},
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_plot_detail_context",
        AsyncMock(return_value=payload),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/plot/1/json")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["plot"] == {"id": 1, "name": "Parcela A"}
    assert body["insights"]["status"] == "ok"


def test_plot_analytics_plot_detail_json_not_found(monkeypatch) -> None:
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_plot_detail_context",
        AsyncMock(return_value=None),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/plot/999/json")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404
    assert response.json() == {"detail": "plot_not_found"}


def test_plot_analytics_comparison_json(monkeypatch) -> None:
    fake_db = _db()
    payload = {
        "sample_size": 2,
        "plots_included": 2,
        "points": [{"x": 10.0, "y": 40.0, "plot_name": "Parcela A"}],
        "efficiency_ranking": [{"plot_name": "Parcela A", "kg_per_m3": 4.0}],
    }
    monkeypatch.setattr(
        "app.routers.plot_analytics.get_multi_plot_comparison",
        AsyncMock(return_value=payload),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.get("/plot-analytics/comparison")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == payload

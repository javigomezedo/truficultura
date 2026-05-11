from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_subscription
from app.database import get_db
from app.main import app
from app.models.truffle_quality import TruffleQuality


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True, active_tenant_id=1)


def _db() -> MagicMock:
    return MagicMock()


def _empty_ctx():
    qualities = [q.value.capitalize() for q in TruffleQuality]
    return {
        "campaigns": [],
        "selected_campaign": None,
        "qualities": qualities,
        "harvest_kg": {q: 0.0 for q in qualities},
        "harvest_count": {},
        "sales_kg": {q: 0.0 for q in qualities},
        "sales_eur": {q: 0.0 for q in qualities},
        "sales_eur_per_kg": {q: 0.0 for q in qualities},
    }


def test_quality_analytics_page_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.quality_analytics.get_quality_analytics_context",
        AsyncMock(return_value=_empty_ctx()),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/quality-analytics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_quality_analytics_page_with_campaign_filter(monkeypatch) -> None:
    ctx = _empty_ctx()
    ctx["selected_campaign"] = 2024
    ctx["campaigns"] = [{"year": 2024, "label": "2024/25"}]
    monkeypatch.setattr(
        "app.routers.quality_analytics.get_quality_analytics_context",
        AsyncMock(return_value=ctx),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.get("/quality-analytics?campaign=2024")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

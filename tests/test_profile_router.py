from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_user
from app.database import get_db
from app.main import app


def _user(**kwargs):
    defaults = dict(
        id=1,
        username="trufero",
        first_name="Juan",
        last_name="García",
        email="juan@example.com",
        role="user",
        is_active=True,
        comunidad_regantes=False,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _db():
    return MagicMock()


def test_profile_page_renders() -> None:
    app.dependency_overrides[require_user] = lambda: _user()
    try:
        client = TestClient(app)
        response = client.get("/profile/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Juan" in response.text
    assert "García" in response.text
    assert "trufero" in response.text


def test_profile_page_without_session_redirects() -> None:
    client = TestClient(app, follow_redirects=False)
    response = client.get("/profile/")
    assert response.status_code in (302, 303)


def test_profile_update_success(monkeypatch) -> None:
    user = _user()
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.profile.update_profile",
        AsyncMock(return_value=user),
    )
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        response = client.post(
            "/profile/",
            data={
                "first_name": "Juan",
                "last_name": "García",
                "username": "trufero",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/")


def test_profile_update_duplicate_username(monkeypatch) -> None:
    user = _user()
    fake_db = _db()
    monkeypatch.setattr(
        "app.routers.profile.update_profile",
        AsyncMock(return_value="El nombre de usuario ya está en uso."),
    )
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/profile/",
            data={
                "first_name": "Juan",
                "last_name": "García",
                "username": "otro_usuario",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "usuario" in response.text.lower()


def test_profile_update_sets_comunidad_regantes(monkeypatch) -> None:
    user = _user()
    fake_db = _db()
    captured: dict = {}

    async def fake_update_profile(
        db, user, first_name, last_name, username, comunidad_regantes
    ):
        captured["comunidad_regantes"] = comunidad_regantes
        return user

    monkeypatch.setattr("app.routers.profile.update_profile", fake_update_profile)
    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: fake_db
    try:
        client = TestClient(app, follow_redirects=False)
        client.post(
            "/profile/",
            data={
                "first_name": "Juan",
                "last_name": "García",
                "username": "trufero",
                "comunidad_regantes": "on",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert captured["comunidad_regantes"] is True

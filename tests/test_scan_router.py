from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models.user import User
from tests.conftest import result


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def _active_user() -> User:
    return User(
        id=1,
        username="javier",
        first_name="Javier",
        last_name="Gomez",
        email="javier@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )


def test_scan_invalid_token_returns_400() -> None:
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/scan/token-invalido")
    assert response.status_code == 400
    assert "QR inválido" in response.text


def test_scan_without_session_redirects_to_login() -> None:
    token = __import__(
        "app.routers.scan", fromlist=["sign_plant_token"]
    ).sign_plant_token(5)

    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get(f"/scan/{token}", follow_redirects=False)

    assert response.status_code == 303
    assert "/login?next=/scan/" in response.headers["location"]


def test_scan_with_session_registers_event(monkeypatch) -> None:
    db = _fake_db()
    db.execute.return_value = result([_active_user()])
    app.dependency_overrides[get_db] = lambda: db

    token = __import__(
        "app.routers.scan", fromlist=["sign_plant_token"]
    ).sign_plant_token(5)
    monkeypatch.setattr(
        "app.routers.scan.plants_service.get_plant",
        AsyncMock(return_value=SimpleNamespace(id=5, plot_id=10, label="A1")),
    )
    monkeypatch.setattr(
        "app.routers.scan.truffle_events_service.create_event",
        AsyncMock(return_value=SimpleNamespace(id=101, created_at=None)),
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    try:
        client = TestClient(app)
        login = client.post(
            "/login",
            data={"username": "javier", "password": "secreto"},
            follow_redirects=False,
        )
        response = client.get(f"/scan/{token}")
    finally:
        app.dependency_overrides.clear()

    assert login.status_code == 303
    assert response.status_code == 200
    assert "Trufa registrada" in response.text


def test_scan_without_session_then_login_returns_and_completes(monkeypatch) -> None:
    db = _fake_db()
    db.execute.return_value = result([_active_user()])
    app.dependency_overrides[get_db] = lambda: db

    token = __import__(
        "app.routers.scan", fromlist=["sign_plant_token"]
    ).sign_plant_token(5)
    monkeypatch.setattr(
        "app.routers.scan.plants_service.get_plant",
        AsyncMock(return_value=SimpleNamespace(id=5, plot_id=10, label="A1")),
    )
    create_mock = AsyncMock(return_value=SimpleNamespace(id=101, created_at=None))
    monkeypatch.setattr(
        "app.routers.scan.truffle_events_service.create_event",
        create_mock,
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    try:
        client = TestClient(app)

        scan_redirect = client.get(f"/scan/{token}", follow_redirects=False)
        assert scan_redirect.status_code == 303
        assert scan_redirect.headers["location"] == f"/login?next=/scan/{token}"

        login = client.post(
            "/login",
            data={"username": "javier", "password": "secreto", "next_url": ""},
            follow_redirects=False,
        )
        assert login.status_code == 303
        assert login.headers["location"] == f"/scan/{token}"

        final_scan = client.get(login.headers["location"], follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert final_scan.status_code == 200
    assert "Trufa registrada" in final_scan.text
    create_mock.assert_awaited_once()

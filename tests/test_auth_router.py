from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.main import app
from app.models.user import User
from tests.conftest import result


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.add = MagicMock()
    return db


def test_login_page_renders_without_session() -> None:
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/login")
    assert response.status_code == 200
    assert "Iniciar sesión" in response.text


def test_login_page_redirects_with_session(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=1,
        username="javier",
        first_name="Javier",
        last_name="Gomez",
        email="javier@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    try:
        client = TestClient(app)
        login = client.post(
            "/login",
            data={"username": "javier", "password": "secreto"},
            follow_redirects=False,
        )
        response = client.get("/login", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert login.status_code == 303
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_register_page_renders_without_session() -> None:
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/register")
    assert response.status_code == 200
    assert "Crear cuenta" in response.text


def test_register_page_redirects_with_session(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=1,
        username="javier",
        first_name="Javier",
        last_name="Gomez",
        email="javier@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    try:
        client = TestClient(app)
        login = client.post(
            "/login",
            data={"username": "javier", "password": "secreto"},
            follow_redirects=False,
        )
        response = client.get("/register", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert login.status_code == 303
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_login_post_success_redirects_and_sets_session(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=1,
        username="javier",
        first_name="Javier",
        last_name="Gomez",
        email="javier@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides.clear()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    try:
        client = TestClient(app)
        response = client.post(
            "/login",
            data={"username": "javier", "password": "secreto"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_login_post_inactive_user_returns_401(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=2,
        username="inactivo",
        first_name="Ina",
        last_name="Ctivo",
        email="inactivo@example.com",
        hashed_password="hash",
        role="user",
        is_active=False,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    try:
        client = TestClient(app)
        response = client.post(
            "/login",
            data={"username": "inactivo", "password": "secreto"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "desactivado" in response.text.lower()


def test_login_post_wrong_credentials_returns_401(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=3,
        username="javier",
        first_name="Javier",
        last_name="Gomez",
        email="javier@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: False)

    try:
        client = TestClient(app)
        response = client.post(
            "/login",
            data={"username": "javier", "password": "incorrecta"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "incorrectos" in response.text.lower()


def test_register_post_password_mismatch_returns_400(monkeypatch) -> None:
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth._user_count", AsyncMock(return_value=1))
    db.execute.return_value = result([])

    try:
        client = TestClient(app)
        response = client.post(
            "/register",
            data={
                "username": "nuevo",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "nuevo@example.com",
                "password": "12345678",
                "password_confirm": "87654321",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "no coinciden" in response.text.lower()


def test_register_post_invalid_email_returns_400(monkeypatch) -> None:
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth._user_count", AsyncMock(return_value=1))

    try:
        client = TestClient(app)
        response = client.post(
            "/register",
            data={
                "username": "nuevo",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "invalido",
                "password": "12345678",
                "password_confirm": "12345678",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "formato v" in response.text.lower()


def test_register_post_existing_email_returns_400(monkeypatch) -> None:
    db = _fake_db()
    existing = User(
        id=9,
        username="existente",
        first_name="Ex",
        last_name="Istente",
        email="existente@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth._user_count", AsyncMock(return_value=1))
    db.execute.return_value = result([existing])

    try:
        client = TestClient(app)
        response = client.post(
            "/register",
            data={
                "username": "nuevo",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "existente@example.com",
                "password": "12345678",
                "password_confirm": "12345678",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "email ya est" in response.text.lower()


def test_register_post_short_password_returns_400(monkeypatch) -> None:
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth._user_count", AsyncMock(return_value=1))
    db.execute.return_value = result([])

    try:
        client = TestClient(app)
        response = client.post(
            "/register",
            data={
                "username": "nuevo",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "nuevo@example.com",
                "password": "1234",
                "password_confirm": "1234",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "al menos 8" in response.text.lower()


def test_register_post_too_long_password_returns_400(monkeypatch) -> None:
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth._user_count", AsyncMock(return_value=1))
    db.execute.return_value = result([])
    long_password = "a" * 73

    try:
        client = TestClient(app)
        response = client.post(
            "/register",
            data={
                "username": "nuevo",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "nuevo@example.com",
                "password": long_password,
                "password_confirm": long_password,
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "demasiado larga" in response.text.lower()


def test_register_post_first_user_redirects(monkeypatch) -> None:
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth._user_count", AsyncMock(return_value=0))
    monkeypatch.setattr("app.routers.auth.hash_password", lambda plain: "hashed")
    db.execute.side_effect = [result([]), MagicMock(), MagicMock(), MagicMock()]

    try:
        client = TestClient(app)
        response = client.post(
            "/register",
            data={
                "username": "primero",
                "first_name": "Primer",
                "last_name": "Usuario",
                "email": "primero@example.com",
                "password": "12345678",
                "password_confirm": "12345678",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?registered=1"
    db.add.assert_called_once()
    db.flush.assert_awaited_once()


def test_logout_clears_session_and_redirects(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=1,
        username="javier",
        first_name="Javier",
        last_name="Gomez",
        email="javier@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    try:
        client = TestClient(app)
        login = client.post(
            "/login",
            data={"username": "javier", "password": "secreto"},
            follow_redirects=False,
        )
        logout = client.post("/logout", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert login.status_code == 303
    assert logout.status_code == 303
    assert logout.headers["location"] == "/login"

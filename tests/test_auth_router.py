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
    db.commit = AsyncMock()
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
        email_confirmed=True,
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


def test_invalid_session_cookie_redirects_to_login_without_500() -> None:
    app.dependency_overrides.clear()
    client = TestClient(app)
    # Simulate stale/corrupted signed cookie from a previous deployment.
    client.cookies.set("session", "this-is-not-a-valid-signed-session")

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


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
        email_confirmed=True,
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
        email_confirmed=True,
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


def test_login_post_success_uses_next_url(monkeypatch) -> None:
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
        email_confirmed=True,
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
            data={
                "username": "javier",
                "password": "secreto",
                "next_url": "/scan/fake-token",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/scan/fake-token"


def test_login_page_prefills_next_url_from_pending_scan(monkeypatch) -> None:
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
        email_confirmed=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    token = __import__(
        "app.routers.scan", fromlist=["sign_plant_token"]
    ).sign_plant_token(5)

    try:
        client = TestClient(app)
        scan_redirect = client.get(f"/scan/{token}", follow_redirects=False)
        response = client.get("/login")
    finally:
        app.dependency_overrides.clear()

    assert scan_redirect.status_code == 303
    assert response.status_code == 200
    assert f'value="/scan/{token}"' in response.text


def test_login_post_uses_pending_scan_when_next_url_empty(monkeypatch) -> None:
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
        email_confirmed=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth.verify_password", lambda plain, hashed: True)

    token = __import__(
        "app.routers.scan", fromlist=["sign_plant_token"]
    ).sign_plant_token(5)

    try:
        client = TestClient(app)
        scan_redirect = client.get(f"/scan/{token}", follow_redirects=False)
        response = client.post(
            "/login",
            data={
                "username": "javier",
                "password": "secreto",
                "next_url": "",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert scan_redirect.status_code == 303
    assert response.status_code == 303
    assert response.headers["location"] == f"/scan/{token}"


def test_login_post_unconfirmed_email_returns_401(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=5,
        username="pendiente",
        first_name="Pen",
        last_name="Diente",
        email="pendiente@example.com",
        hashed_password="hash",
        role="user",
        is_active=False,
        email_confirmed=False,
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
            data={"username": "pendiente", "password": "secreto"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert "confirmar" in response.text.lower()


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
        email_confirmed=True,
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
        email_confirmed=True,
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
    # Ensure no ADMIN_EMAIL so is_first_user=True triggers the admin/confirmed path
    monkeypatch.setattr("app.routers.auth.settings", type("S", (), {"ADMIN_EMAIL": "", "smtp_configured": False})())
    # First execute: check existing email. Next three: update Plot, Expense, Income.
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
    db.commit.assert_awaited_once()


def test_register_post_second_user_sends_confirmation_without_smtp(monkeypatch) -> None:
    """Without SMTP, the account is activated directly and redirected to registered=1."""
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth._user_count", AsyncMock(return_value=1))
    monkeypatch.setattr("app.routers.auth.hash_password", lambda plain: "hashed")
    monkeypatch.setattr(
        "app.routers.auth.settings",
        type(
            "S",
            (),
            {
                "ADMIN_EMAIL": None,
                "smtp_configured": False,
                "APP_BASE_URL": "http://localhost",
            },
        )(),
    )
    db.execute.return_value = result([])

    try:
        client = TestClient(app)
        response = client.post(
            "/register",
            data={
                "username": "segundo",
                "first_name": "Segundo",
                "last_name": "Usuario",
                "email": "segundo@example.com",
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


def test_register_post_second_user_pending_confirmation_with_smtp(monkeypatch) -> None:
    """With SMTP configured, the user gets a confirmation email and redirects to pending."""
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr("app.routers.auth._user_count", AsyncMock(return_value=1))
    monkeypatch.setattr("app.routers.auth.hash_password", lambda plain: "hashed")
    monkeypatch.setattr(
        "app.routers.auth.settings",
        type(
            "S",
            (),
            {
                "ADMIN_EMAIL": None,
                "smtp_configured": True,
                "APP_BASE_URL": "http://localhost",
            },
        )(),
    )
    send_mock = AsyncMock()
    monkeypatch.setattr("app.routers.auth.send_confirmation_email", send_mock)
    db.execute.return_value = result([])

    try:
        client = TestClient(app)
        response = client.post(
            "/register",
            data={
                "username": "segundo",
                "first_name": "Segundo",
                "last_name": "Usuario",
                "email": "segundo@example.com",
                "password": "12345678",
                "password_confirm": "12345678",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?pending_confirmation=1"
    send_mock.assert_awaited_once()


def test_register_confirm_valid_token_activates_account(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=10,
        username="nuevo",
        first_name="Nuevo",
        last_name="Usuario",
        email="nuevo@example.com",
        hashed_password="hash",
        role="user",
        is_active=False,
        email_confirmed=False,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr(
        "app.routers.auth.confirm_token",
        lambda token, salt, max_age: "nuevo@example.com",
    )

    try:
        client = TestClient(app)
        response = client.get("/register/confirm/fake-token", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?confirmed=1"
    assert user.email_confirmed is True
    assert user.is_active is True
    db.commit.assert_awaited_once()


def test_register_confirm_invalid_token_redirects_to_error(monkeypatch) -> None:
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr(
        "app.routers.auth.confirm_token",
        lambda token, salt, max_age: None,
    )

    try:
        client = TestClient(app)
        response = client.get("/register/confirm/bad-token", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?confirm_error=1"


def test_register_confirm_already_confirmed_redirects(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=11,
        username="ya",
        first_name="Ya",
        last_name="Confirmado",
        email="ya@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
        email_confirmed=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr(
        "app.routers.auth.confirm_token",
        lambda token, salt, max_age: "ya@example.com",
    )

    try:
        client = TestClient(app)
        response = client.get("/register/confirm/old-token", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?already_confirmed=1"


def test_forgot_password_page_renders() -> None:
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/forgot-password")
    assert response.status_code == 200
    assert "contrase" in response.text.lower()


def test_forgot_password_post_sends_email_when_smtp_configured(monkeypatch) -> None:
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
        email_confirmed=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr(
        "app.routers.auth.settings",
        type(
            "S",
            (),
            {
                "ADMIN_EMAIL": None,
                "smtp_configured": True,
                "APP_BASE_URL": "http://localhost",
            },
        )(),
    )
    send_mock = AsyncMock()
    monkeypatch.setattr("app.routers.auth.send_password_reset_email", send_mock)
    monkeypatch.setattr("app.routers.auth.generate_token", lambda payload, salt: "tok")

    try:
        client = TestClient(app)
        response = client.post(
            "/forgot-password",
            data={"email": "javier@example.com"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?reset_sent=1"
    send_mock.assert_awaited_once()


def test_forgot_password_post_nonexistent_email_still_redirects(monkeypatch) -> None:
    """Avoids email enumeration: same response regardless of whether the email exists."""
    db = _fake_db()
    db.execute.return_value = result([])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr(
        "app.routers.auth.settings",
        type(
            "S",
            (),
            {
                "ADMIN_EMAIL": None,
                "smtp_configured": True,
                "APP_BASE_URL": "http://localhost",
            },
        )(),
    )

    try:
        client = TestClient(app)
        response = client.post(
            "/forgot-password",
            data={"email": "noexiste@example.com"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?reset_sent=1"


def test_reset_password_page_invalid_token_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.auth.confirm_token",
        lambda token, salt, max_age: None,
    )
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/reset-password/bad-token", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login?reset_error=1"


def test_reset_password_page_valid_token_renders(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.auth.confirm_token",
        lambda token, salt, max_age: "javier@example.com",
    )
    app.dependency_overrides.clear()
    client = TestClient(app)
    response = client.get("/reset-password/valid-token")
    assert response.status_code == 200
    assert "contrase" in response.text.lower()


def test_reset_password_post_updates_password(monkeypatch) -> None:
    db = _fake_db()
    user = User(
        id=1,
        username="javier",
        first_name="Javier",
        last_name="Gomez",
        email="javier@example.com",
        hashed_password="oldhash",
        role="user",
        is_active=True,
        email_confirmed=True,
    )
    db.execute.return_value = result([user])
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr(
        "app.routers.auth.confirm_token",
        lambda token, salt, max_age: "javier@example.com",
    )
    monkeypatch.setattr("app.routers.auth.hash_password", lambda plain: "newhash")

    try:
        client = TestClient(app)
        response = client.post(
            "/reset-password/valid-token",
            data={"password": "newpassword1", "password_confirm": "newpassword1"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?password_reset=1"
    assert user.hashed_password == "newhash"
    db.commit.assert_awaited_once()


def test_reset_password_post_mismatch_returns_400(monkeypatch) -> None:
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr(
        "app.routers.auth.confirm_token",
        lambda token, salt, max_age: "javier@example.com",
    )

    try:
        client = TestClient(app)
        response = client.post(
            "/reset-password/valid-token",
            data={"password": "newpassword1", "password_confirm": "different"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "no coinciden" in response.text.lower()


def test_reset_password_post_invalid_token_redirects_to_error(monkeypatch) -> None:
    db = _fake_db()
    app.dependency_overrides[__import__("app.database", fromlist=["get_db"]).get_db] = (
        lambda: db
    )
    monkeypatch.setattr(
        "app.routers.auth.confirm_token",
        lambda token, salt, max_age: None,
    )

    try:
        client = TestClient(app)
        response = client.post(
            "/reset-password/bad-token",
            data={"password": "newpassword1", "password_confirm": "newpassword1"},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/login?reset_error=1"


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
        email_confirmed=True,
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

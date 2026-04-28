from __future__ import annotations

import datetime
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_admin
from app.database import get_db
from app.main import app
from app.models.user import User
from tests.conftest import result


def _admin_user() -> User:
    return User(
        id=1,
        username="admin",
        first_name="Admin",
        last_name="User",
        email="admin@example.com",
        hashed_password="hash",
        role="admin",
        is_active=True,
        created_at=datetime.datetime(2026, 4, 3, 10, 0, 0),
    )


def _normal_user() -> User:
    return User(
        id=2,
        username="pepe",
        first_name="Pepe",
        last_name="Perez",
        email="pepe@example.com",
        hashed_password="hash",
        role="user",
        is_active=True,
        created_at=datetime.datetime(2026, 4, 2, 10, 0, 0),
    )


def _fake_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


def test_admin_users_list_renders() -> None:
    db = _fake_db()
    db.execute.return_value = result(
        [
            _admin_user(),
            User(
                id=2,
                username="pepe",
                first_name="Pepe",
                last_name="Perez",
                email="pepe@example.com",
                hashed_password="hash",
                role="user",
                is_active=True,
                created_at=datetime.datetime(2026, 4, 2, 10, 0, 0),
            ),
        ]
    )

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/users")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "pepe" in response.text


def test_admin_deactivate_self_redirects_without_commit() -> None:
    db = _fake_db()

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/admin/users/1/deactivate", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users?error=no-self-delete"
    db.commit.assert_not_called()


def test_admin_create_user_page_returns_404() -> None:
    """The create-user endpoint has been removed; admin cannot create users anymore."""
    db = _fake_db()

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/users/create", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    # The route no longer exists; FastAPI returns 404 or 405 depending on path matching
    assert response.status_code in (404, 405)


def test_admin_edit_user_page_not_found_redirects() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/users/99/edit", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"


def test_admin_edit_user_page_renders() -> None:
    db = _fake_db()
    db.execute.return_value = result([_normal_user()])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/users/2/edit")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "pepe@example.com" in response.text


def test_admin_update_user_not_found_redirects() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users/99",
            data={
                "username": "nuevo",
                "first_name": "N",
                "last_name": "U",
                "email": "nuevo@example.com",
                "role": "user",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"


def test_admin_update_user_duplicate_username_returns_400() -> None:
    db = _fake_db()
    db.execute.side_effect = [result([_normal_user()]), result([_admin_user()])]

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users/2",
            data={
                "username": "admin",
                "first_name": "Pepe",
                "last_name": "Perez",
                "email": "pepe@example.com",
                "role": "user",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "usuario ya existe" in response.text.lower()


def test_admin_update_user_invalid_email_returns_400() -> None:
    db = _fake_db()
    db.execute.return_value = result([_normal_user()])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users/2",
            data={
                "username": "pepe",
                "first_name": "Pepe",
                "last_name": "Perez",
                "email": "email-invalido",
                "role": "user",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "formato v" in response.text.lower()


def test_admin_update_user_existing_email_returns_400() -> None:
    db = _fake_db()
    user = _normal_user()
    db.execute.side_effect = [result([user]), result([_admin_user()])]

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users/2",
            data={
                "username": "pepe",
                "first_name": "Pepe",
                "last_name": "Perez",
                "email": "admin@example.com",
                "role": "user",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "email ya est" in response.text.lower()


def test_admin_update_user_role_is_auto_computed_as_user() -> None:
    """Role is never accepted from the form; non-first, non-admin-email users become 'user'."""
    db = _fake_db()
    user = _normal_user()
    # Execute calls: find user, check new username, check new email, get min(User.id)
    db.execute.side_effect = [result([user]), result([]), result([]), result([1])]

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users/2",
            data={
                "username": "nuevo_pepe",
                "first_name": "Pepe",
                "last_name": "Perez",
                "email": "nuevopepe@example.com",
                # role field is ignored; not sent at all (or sent with any value)
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert user.username == "nuevo_pepe"
    assert user.role == "user"
    db.commit.assert_awaited_once()


def test_admin_update_user_first_user_gets_admin_role() -> None:
    """The user with the minimum ID is always assigned the admin role."""
    db = _fake_db()
    user = _normal_user()  # id=2, but will be treated as first user
    user.id = 1  # make it the first user
    # Execute calls: find user, check new username, check new email, get min(User.id)=1
    db.execute.side_effect = [result([user]), result([]), result([]), result([1])]

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users/1",
            data={
                "username": "nuevo_pepe",
                "first_name": "Pepe",
                "last_name": "Perez",
                "email": "nuevopepe@example.com",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert user.role == "admin"
    db.commit.assert_awaited_once()


def test_admin_deactivate_user_not_found_redirects() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/admin/users/99/deactivate", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"


def test_admin_deactivate_user_success() -> None:
    db = _fake_db()
    user = _normal_user()
    db.execute.return_value = result([user])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/admin/users/2/deactivate", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert user.is_active is False
    db.commit.assert_awaited_once()


def test_admin_activate_user_not_found_redirects() -> None:
    db = _fake_db()
    db.execute.return_value = result([])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/admin/users/99/activate", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"


def test_admin_activate_user_success() -> None:
    db = _fake_db()
    user = _normal_user()
    user.is_active = False
    db.execute.return_value = result([user])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/admin/users/2/activate", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert user.is_active is True
    db.commit.assert_awaited_once()


def test_admin_lluvia_importar_ibericam_form_uses_sitemap(monkeypatch) -> None:
    """Cuando el municipio no está en el dict estático, busca en el sitemap."""
    import app.routers.admin as admin_mod

    db = _fake_db()
    # Overview con nombre del municipio para que find_ibericam_slug_for_municipio funcione
    monkeypatch.setattr(
        admin_mod,
        "get_admin_rainfall_overview",
        AsyncMock(
            return_value=[
                {
                    "municipio_cod": "44158",
                    "municipio_name": "Mora De Rubielos",
                    "aemet_hasta": None,
                    "ibericam_hasta": None,
                }
            ]
        ),
    )
    # Simula el sitemap devolviendo el slug de mora-de-rubielos
    monkeypatch.setattr(
        admin_mod,
        "fetch_ibericam_sitemap_slugs",
        AsyncMock(return_value={"mora-de-rubielos", "sarrion"}),
    )

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/lluvia/44158/importar/ibericam")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "mora-de-rubielos" in response.text


def test_admin_lluvia_importar_ibericam_form_sitemap_error_graceful(
    monkeypatch,
) -> None:
    """Si el sitemap falla, el formulario se muestra igualmente con campo vacío."""
    import app.routers.admin as admin_mod

    db = _fake_db()
    monkeypatch.setattr(
        admin_mod,
        "get_admin_rainfall_overview",
        AsyncMock(return_value=[]),
    )
    monkeypatch.setattr(
        admin_mod,
        "fetch_ibericam_sitemap_slugs",
        AsyncMock(side_effect=Exception("timeout")),
    )

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/lluvia/44999/importar/ibericam")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200

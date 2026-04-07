from __future__ import annotations

import datetime
import io
from types import SimpleNamespace
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


def test_admin_create_user_invalid_email_returns_400() -> None:
    db = _fake_db()

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users",
            data={
                "username": "nuevo",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "email-invalido",
                "password": "12345678",
                "role": "user",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "formato v" in response.text.lower()


def test_admin_create_user_success_redirects(monkeypatch) -> None:
    db = _fake_db()
    db.execute.side_effect = [result([]), result([])]
    monkeypatch.setattr("app.routers.admin.hash_password", lambda plain: "hashed")

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users",
            data={
                "username": "nuevo",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "nuevo@example.com",
                "password": "12345678",
                "role": "admin",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"
    db.add.assert_called_once()
    db.commit.assert_awaited_once()


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


def test_admin_create_user_page_renders() -> None:
    db = _fake_db()

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/users/create")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Crear" in response.text


def test_admin_create_user_existing_username_returns_400() -> None:
    db = _fake_db()
    db.execute.return_value = result([_normal_user()])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users",
            data={
                "username": "pepe",
                "first_name": "Pepe",
                "last_name": "Perez",
                "email": "otro@example.com",
                "password": "12345678",
                "role": "user",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "usuario ya existe" in response.text.lower()


def test_admin_create_user_existing_email_returns_400() -> None:
    db = _fake_db()
    db.execute.side_effect = [result([]), result([_normal_user()])]

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users",
            data={
                "username": "nuevo",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "pepe@example.com",
                "password": "12345678",
                "role": "user",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "email ya est" in response.text.lower()


def test_admin_create_user_invalid_role_defaults_to_user(monkeypatch) -> None:
    db = _fake_db()
    db.execute.side_effect = [result([]), result([])]
    monkeypatch.setattr("app.routers.admin.hash_password", lambda plain: "hashed")

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/admin/users",
            data={
                "username": "nuevo2",
                "first_name": "Nuevo",
                "last_name": "Usuario",
                "email": "nuevo2@example.com",
                "password": "12345678",
                "role": "root",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    created_user = db.add.call_args.args[0]
    assert created_user.role == "user"


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


def test_admin_update_user_success_with_invalid_role_defaults_user() -> None:
    db = _fake_db()
    user = _normal_user()
    db.execute.side_effect = [result([user]), result([]), result([])]

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
                "role": "superadmin",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert user.username == "nuevo_pepe"
    assert user.role == "user"
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


def test_admin_qr_management_page_renders_users() -> None:
    db = _fake_db()
    db.execute.return_value = result([_admin_user(), _normal_user()])

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/qr")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "QR por Parcelas" in response.text
    assert "admin" in response.text


def test_admin_qr_management_page_loads_plots_for_selected_user() -> None:
    db = _fake_db()
    db.execute.side_effect = [
        result([_admin_user(), _normal_user()]),
        result([SimpleNamespace(id=10, name="Parcela Norte")]),
    ]

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/qr?user_id=2")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Parcela Norte" in response.text


def test_admin_qr_pdf_redirects_when_plot_not_found(monkeypatch) -> None:
    db = _fake_db()

    monkeypatch.setattr(
        "app.services.plots_service.get_plot",
        AsyncMock(return_value=None),
    )

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/users/2/plots/10/qr-pdf", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/users"


def test_admin_qr_pdf_redirects_when_no_plants(monkeypatch) -> None:
    db = _fake_db()

    monkeypatch.setattr(
        "app.services.plots_service.get_plot",
        AsyncMock(return_value=SimpleNamespace(id=10, name="Parcela Norte")),
    )
    monkeypatch.setattr(
        "app.services.plants_service.list_plants",
        AsyncMock(return_value=[]),
    )

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/users/2/plots/10/qr-pdf", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "no+tiene+plantas+configuradas" in response.headers["location"]


def test_admin_qr_pdf_returns_pdf_file(monkeypatch) -> None:
    db = _fake_db()

    monkeypatch.setattr(
        "app.services.plots_service.get_plot",
        AsyncMock(return_value=SimpleNamespace(id=10, name="Parcela Norte")),
    )
    monkeypatch.setattr(
        "app.services.plants_service.list_plants",
        AsyncMock(
            return_value=[
                SimpleNamespace(id=1, label="A1"),
                SimpleNamespace(id=2, label="A2"),
            ]
        ),
    )
    monkeypatch.setattr(
        "app.routers.scan.sign_plant_token", lambda plant_id: f"tok-{plant_id}"
    )

    class _FakeQrImage:
        def save(self, buffer: io.BytesIO, format: str = "PNG") -> None:
            buffer.write(b"fake-png")

    class _FakePdf:
        def __init__(self, *args, **kwargs):
            pass

        def set_auto_page_break(self, auto: bool = False) -> None:
            pass

        def add_page(self) -> None:
            pass

        def image(self, *args, **kwargs) -> None:
            pass

        def set_font(self, *args, **kwargs) -> None:
            pass

        def set_xy(self, *args, **kwargs) -> None:
            pass

        def cell(self, *args, **kwargs) -> None:
            pass

        def output(self):
            return b"%PDF-FAKE"

    monkeypatch.setattr("qrcode.make", lambda _url: _FakeQrImage())
    monkeypatch.setattr("fpdf.FPDF", _FakePdf)

    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/admin/users/2/plots/10/qr-pdf")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert "attachment;" in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")

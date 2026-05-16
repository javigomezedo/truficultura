from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_admin, require_subscription
from app.database import get_db
from app.main import app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _user(tenant_id: int = 1) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        role="user",
        is_active=True,
        active_tenant_id=tenant_id,
        first_name="Juan",
        last_name="García",
        email="juan@example.com",
    )


def _admin_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=99,
        role="admin",
        is_active=True,
        active_tenant_id=1,
        first_name="Admin",
        last_name="User",
        email="admin@example.com",
    )


def _fake_db() -> MagicMock:
    return MagicMock()


def _fake_incident(
    incident_id: int = 1,
    tenant_id: int = 1,
    resolved: bool = False,
    has_attachment: bool = False,
    has_admin_response: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=incident_id,
        tenant_id=tenant_id,
        user_id=1,
        title="Error en el botón guardar",
        description="Al pulsar guardar no ocurre nada.",
        category="boton_roto",
        category_label="Botón roto",
        severity="alta",
        severity_label="Alta",
        resolved=resolved,
        admin_response="Corregido en v1.2" if has_admin_response else None,
        created_at=datetime.datetime(2026, 1, 15, 10, 0, 0),
        resolved_at=datetime.datetime(2026, 1, 16, 9, 0, 0) if resolved else None,
        attachment_filename="captura.png" if has_attachment else None,
        attachment_data=b"fake-image-bytes" if has_attachment else None,
        attachment_content_type="image/png" if has_attachment else None,
        user=SimpleNamespace(
            first_name="Juan",
            last_name="García",
            email="juan@example.com",
        ),
        tenant=SimpleNamespace(name="Mi Finca"),
    )


# ---------------------------------------------------------------------------
# User routes — list
# ---------------------------------------------------------------------------


def test_list_incidents_renders_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_incidents_by_tenant",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "incidencias" in response.text.lower()


def test_list_incidents_renders_with_incidents(monkeypatch) -> None:
    incidents = [_fake_incident(1), _fake_incident(2)]
    monkeypatch.setattr(
        "app.services.incidents_service.get_incidents_by_tenant",
        AsyncMock(return_value=incidents),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Error en el botón guardar" in response.text


def test_list_incidents_shows_msg_param(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_incidents_by_tenant",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/?msg=Incidencia+registrada")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Incidencia" in response.text


# ---------------------------------------------------------------------------
# User routes — new form
# ---------------------------------------------------------------------------


def test_new_incident_form_renders() -> None:
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/new")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Reportar" in response.text
    assert "category" in response.text
    assert "severity" in response.text


# ---------------------------------------------------------------------------
# User routes — create
# ---------------------------------------------------------------------------


def test_create_incident_without_attachment_redirects(monkeypatch) -> None:
    fake_inc = _fake_incident()
    monkeypatch.setattr(
        "app.services.incidents_service.create_incident",
        AsyncMock(return_value=fake_inc),
    )
    monkeypatch.setattr(
        "app.services.email_service.send_incident_notification",
        AsyncMock(),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incidents/",
            data={
                "title": "Error en el botón",
                "description": "Al pulsar guardar no pasa nada.",
                "category": "boton_roto",
                "severity": "alta",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/incidents/" in response.headers["location"]


def test_create_incident_with_valid_attachment_redirects(monkeypatch) -> None:
    fake_inc = _fake_incident(has_attachment=True)
    monkeypatch.setattr(
        "app.services.incidents_service.create_incident",
        AsyncMock(return_value=fake_inc),
    )
    monkeypatch.setattr(
        "app.services.email_service.send_incident_notification",
        AsyncMock(),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incidents/",
            data={
                "title": "Error visual",
                "description": "Captura adjunta.",
                "category": "error_visual",
                "severity": "baja",
            },
            files={"attachment": ("captura.png", b"fake-image-data", "image/png")},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


def test_create_incident_invalid_mime_type_shows_error(monkeypatch) -> None:
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incidents/",
            data={
                "title": "Error",
                "description": "Algo está mal.",
                "category": "otro",
                "severity": "media",
            },
            files={"attachment": ("script.js", b"alert('xss')", "text/javascript")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "no permitido" in response.text.lower()


def test_create_incident_file_too_large_shows_error(monkeypatch) -> None:
    large_data = b"x" * (5 * 1024 * 1024 + 1)  # 5 MB + 1 byte
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incidents/",
            data={
                "title": "Error",
                "description": "Algo está mal.",
                "category": "otro",
                "severity": "media",
            },
            files={"attachment": ("big.jpg", large_data, "image/jpeg")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422
    assert "5 mb" in response.text.lower()


def test_create_incident_email_failure_is_silenced(monkeypatch) -> None:
    """Un error en el email no debe impedir la creación de la incidencia."""
    fake_inc = _fake_incident()
    monkeypatch.setattr(
        "app.services.incidents_service.create_incident",
        AsyncMock(return_value=fake_inc),
    )
    monkeypatch.setattr(
        "app.services.email_service.send_incident_notification",
        AsyncMock(side_effect=RuntimeError("SMTP down")),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incidents/",
            data={
                "title": "Error",
                "description": "Algo está mal.",
                "category": "otro",
                "severity": "media",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


def test_create_incident_invalid_category_normalised(monkeypatch) -> None:
    """Categoría desconocida se normaliza a 'otro'."""
    created: list = []

    async def capture_create(db, tenant_id, user_id, title, description, category, severity, **kw):
        inc = _fake_incident()
        inc.category = category
        created.append(category)
        return inc

    monkeypatch.setattr("app.services.incidents_service.create_incident", capture_create)
    monkeypatch.setattr("app.services.email_service.send_incident_notification", AsyncMock())
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        client.post(
            "/incidents/",
            data={
                "title": "Test",
                "description": "Test",
                "category": "categoria_inexistente",
                "severity": "media",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert created[0] == "otro"


# ---------------------------------------------------------------------------
# User routes — detail
# ---------------------------------------------------------------------------


def test_detail_incident_renders(monkeypatch) -> None:
    inc = _fake_incident(incident_id=3, tenant_id=1)
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_subscription] = lambda: _user(tenant_id=1)
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Error en el botón guardar" in response.text


def test_detail_incident_resolved_shows_response(monkeypatch) -> None:
    inc = _fake_incident(incident_id=3, tenant_id=1, resolved=True, has_admin_response=True)
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_subscription] = lambda: _user(tenant_id=1)
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/3")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Corregido en v1.2" in response.text


def test_detail_incident_not_found_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/999", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/incidents/" in response.headers["location"]


def test_detail_incident_wrong_tenant_redirects(monkeypatch) -> None:
    """Un usuario no puede ver incidencias de otro tenant."""
    inc = _fake_incident(incident_id=5, tenant_id=99)  # tenant diferente
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_subscription] = lambda: _user(tenant_id=1)
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/5", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/incidents/" in response.headers["location"]


# ---------------------------------------------------------------------------
# User routes — attachment download
# ---------------------------------------------------------------------------


def test_download_attachment_not_found_returns_404(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/99/attachment")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_download_attachment_no_data_returns_404(monkeypatch) -> None:
    inc = _fake_incident(incident_id=1, tenant_id=1, has_attachment=False)
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_subscription] = lambda: _user(tenant_id=1)
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/1/attachment")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_download_attachment_image_streams(monkeypatch) -> None:
    inc = _fake_incident(incident_id=1, tenant_id=1, has_attachment=True)
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_subscription] = lambda: _user(tenant_id=1)
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/1/attachment")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"fake-image-bytes"
    assert "image/png" in response.headers["content-type"]


def test_download_attachment_wrong_tenant_returns_404(monkeypatch) -> None:
    inc = _fake_incident(incident_id=1, tenant_id=99, has_attachment=True)
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_subscription] = lambda: _user(tenant_id=1)
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/1/attachment")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Admin routes — list
# ---------------------------------------------------------------------------


def test_admin_list_incidents_renders(monkeypatch) -> None:
    incidents = [_fake_incident(1), _fake_incident(2, resolved=True)]
    monkeypatch.setattr(
        "app.services.incidents_service.get_all_incidents_admin",
        AsyncMock(return_value=incidents),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/list")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Error en el botón guardar" in response.text


def test_admin_list_incidents_empty(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_all_incidents_admin",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/list")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "0" in response.text


def test_admin_list_incidents_with_resolved_filter(monkeypatch) -> None:
    resolved_inc = _fake_incident(1, resolved=True)
    monkeypatch.setattr(
        "app.services.incidents_service.get_all_incidents_admin",
        AsyncMock(return_value=[resolved_inc]),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/list?resolved=true")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


def test_admin_list_incidents_with_category_filter(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_all_incidents_admin",
        AsyncMock(return_value=[]),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/list?category=error_sistema&severity=critica")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Admin routes — detail
# ---------------------------------------------------------------------------


def test_admin_detail_incident_renders(monkeypatch) -> None:
    inc = _fake_incident(incident_id=7)
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/7")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Error en el botón guardar" in response.text
    assert "Marcar como resuelta" in response.text


def test_admin_detail_incident_resolved_hides_form(monkeypatch) -> None:
    inc = _fake_incident(incident_id=7, resolved=True, has_admin_response=True)
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/7")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Marcar como resuelta" not in response.text
    assert "Corregido en v1.2" in response.text


def test_admin_detail_incident_not_found_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/999", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "admin/list" in response.headers["location"]


# ---------------------------------------------------------------------------
# Admin routes — resolve
# ---------------------------------------------------------------------------


def test_admin_resolve_incident_redirects(monkeypatch) -> None:
    inc = _fake_incident(incident_id=10, resolved=False)
    resolved_inc = _fake_incident(incident_id=10, resolved=True, has_admin_response=True)
    resolved_inc.user.email = "juan@example.com"

    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    monkeypatch.setattr(
        "app.services.incidents_service.resolve_incident",
        AsyncMock(return_value=resolved_inc),
    )
    monkeypatch.setattr(
        "app.services.email_service.send_incident_resolved_email",
        AsyncMock(),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incidents/admin/10/resolve",
            data={"admin_response": "Hemos corregido el error."},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "/incidents/admin/10" in response.headers["location"]
    assert "resolved=1" in response.headers["location"]


def test_admin_resolve_incident_not_found_redirects(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incidents/admin/999/resolve",
            data={"admin_response": "Nada que hacer."},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert "admin/list" in response.headers["location"]


def test_admin_resolve_email_failure_is_silenced(monkeypatch) -> None:
    """Un error al enviar el email de resolución no debe romper el flujo."""
    inc = _fake_incident(incident_id=11, resolved=False)
    resolved_inc = _fake_incident(incident_id=11, resolved=True, has_admin_response=True)

    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    monkeypatch.setattr(
        "app.services.incidents_service.resolve_incident",
        AsyncMock(return_value=resolved_inc),
    )
    monkeypatch.setattr(
        "app.services.email_service.send_incident_resolved_email",
        AsyncMock(side_effect=RuntimeError("SMTP down")),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.post(
            "/incidents/admin/11/resolve",
            data={"admin_response": "Arreglado."},
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303


# ---------------------------------------------------------------------------
# Admin routes — attachment download
# ---------------------------------------------------------------------------


def test_admin_download_attachment_streams(monkeypatch) -> None:
    inc = _fake_incident(incident_id=5, has_attachment=True)
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=inc),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/5/attachment")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"fake-image-bytes"


def test_admin_download_attachment_not_found(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.services.incidents_service.get_incident_by_id",
        AsyncMock(return_value=None),
    )
    app.dependency_overrides[require_admin] = _admin_user
    app.dependency_overrides[get_db] = _fake_db
    try:
        client = TestClient(app)
        response = client.get("/incidents/admin/999/attachment")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404

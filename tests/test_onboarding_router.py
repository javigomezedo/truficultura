"""Tests for the onboarding router (Fase 0 — without LLM nodes)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.auth import require_subscription
from app.config import settings
from app.database import get_db
from app.main import app
from app.plan_access import require_write_access
from app.services import onboarding_service

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "onboarding"


def _override_user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True, active_tenant_id=42)


def _fake_db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock(), flush=AsyncMock())


@pytest.fixture(autouse=True)
def _mock_onboarding_quota(monkeypatch):
    """Default quota mock + ensure require_subscription is overridden for write endpoints."""

    async def _zero(_db, *, tenant_id, now=None):
        return 0

    monkeypatch.setattr(onboarding_service, "count_sessions_this_month", _zero)
    # Always override require_subscription so the feature/quota dep chain resolves
    # in tests that historically only overrode require_write_access.
    app.dependency_overrides.setdefault(require_subscription, _override_user)
    yield


def test_app_registers_onboarding_routes() -> None:
    paths = {route.path for route in app.routes}
    assert "/onboarding/" in paths
    assert "/onboarding/upload" in paths
    assert "/onboarding/{session_id}" in paths
    assert "/onboarding/{session_id}/cancel" in paths


def test_index_renders(monkeypatch) -> None:
    async def fake_list(_db, *, tenant_id, limit=50):
        return []

    monkeypatch.setattr(onboarding_service, "list_sessions", fake_list)

    db = _fake_db()
    app.dependency_overrides[require_subscription] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/onboarding/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importación inteligente" in response.text
    assert "Subir un fichero Excel" in response.text


def test_upload_rejects_non_excel(monkeypatch) -> None:
    async def fake_list(_db, *, tenant_id, limit=50):
        return []

    monkeypatch.setattr(onboarding_service, "list_sessions", fake_list)

    db = _fake_db()
    app.dependency_overrides[require_subscription] = _override_user
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/onboarding/upload",
            files={"file": ("notas.txt", b"hola mundo", "text/plain")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Formato no soportado" in response.text


def test_upload_creates_session_and_redirects(monkeypatch) -> None:
    captured: dict = {}

    async def fake_create_session(
        _db,
        *,
        tenant_id,
        created_by_user_id,
        original_filename,
        initial_state,
        status,
        entity_type=None,
        raw_file=None,
    ):
        captured["tenant_id"] = tenant_id
        captured["filename"] = original_filename
        captured["state"] = initial_state
        captured["status"] = status
        captured["raw_file_size"] = len(raw_file) if raw_file else 0
        return SimpleNamespace(id=99, state_json=initial_state, raw_file=raw_file)

    monkeypatch.setattr(onboarding_service, "create_session", fake_create_session)
    # Disable LLM agent execution in this test
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    db = _fake_db()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        with (FIXTURES / "gastos_cabeceras_irregulares.xlsx").open("rb") as fh:
            response = client.post(
                "/onboarding/upload",
                files={
                    "file": (
                        "gastos.xlsx",
                        fh,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/onboarding/99"
    assert captured["tenant_id"] == 42
    assert captured["filename"] == "gastos.xlsx"
    assert captured["status"] == "uploaded"
    state = captured["state"]
    assert state["sheet_name"] == "Gastos 2025"
    assert state["headers"][0] == "Fecha"
    assert state["total_rows"] == 4
    db.commit.assert_awaited()


def test_session_detail_404_for_other_tenant(monkeypatch) -> None:
    async def fake_get_session(_db, _id, tenant_id):
        return None

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)

    db = _fake_db()
    app.dependency_overrides[require_subscription] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/onboarding/123")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_session_detail_renders_preview(monkeypatch) -> None:
    fake_session = SimpleNamespace(
        id=7,
        original_filename="gastos.xlsx",
        status="uploaded",
        entity_type=None,
        error_message=None,
        state_json={
            "sheet_name": "Gastos 2025",
            "headers": ["Fecha", "Concepto", "Importe"],
            "sample_rows": [["2025-01-01", "Pienso", 21.0]],
            "total_rows": 1,
        },
    )

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)

    db = _fake_db()
    app.dependency_overrides[require_subscription] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.get("/onboarding/7")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "gastos.xlsx" in response.text
    assert "Gastos 2025" in response.text
    assert "Pienso" in response.text


def test_upload_runs_agent_when_api_key_present(monkeypatch) -> None:
    """When OPENAI_API_KEY is set, the upload endpoint runs the LangGraph
    agent and persists the resulting state."""
    captured: dict = {}

    async def fake_create_session(_db, **kwargs):
        return SimpleNamespace(
            id=42, state_json=kwargs["initial_state"], raw_file=kwargs.get("raw_file")
        )

    async def fake_update(
        _db,
        session,
        *,
        state=None,
        status=None,
        entity_type=None,
        error_message=None,
    ):
        captured["state"] = state
        captured["status"] = status
        captured["entity_type"] = entity_type
        return session

    def fake_build_graph():
        def _run(state):
            return {
                **state,
                "entity_type": "gastos",
                "entity_confidence": 0.9,
                "proposed_mapping": [],
            }

        return _run

    monkeypatch.setattr(onboarding_service, "create_session", fake_create_session)
    monkeypatch.setattr(onboarding_service, "update_session_state", fake_update)
    monkeypatch.setattr("app.routers.onboarding.build_graph", fake_build_graph)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")

    db = _fake_db()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        with (FIXTURES / "gastos_cabeceras_irregulares.xlsx").open("rb") as fh:
            response = client.post(
                "/onboarding/upload",
                files={
                    "file": (
                        "gastos.xlsx",
                        fh,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert captured["status"] == "awaiting_user"
    assert captured["entity_type"] == "gastos"
    assert captured["state"]["entity_confidence"] == 0.9


def test_run_agent_endpoint(monkeypatch) -> None:
    fake_session = SimpleNamespace(
        id=7,
        original_filename="gastos.xlsx",
        status="uploaded",
        entity_type=None,
        error_message=None,
        state_json={"headers": ["A"], "sample_rows": []},
    )
    captured: dict = {}

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    async def fake_update(_db, session, **kwargs):
        captured.update(kwargs)
        return session

    def fake_build_graph():
        return lambda state: {
            **state,
            "entity_type": "ingresos",
            "entity_confidence": 0.8,
        }

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)
    monkeypatch.setattr(onboarding_service, "update_session_state", fake_update)
    monkeypatch.setattr("app.routers.onboarding.build_graph", fake_build_graph)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", "sk-test")

    db = _fake_db()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/onboarding/7/run-agent", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/onboarding/7"
    assert captured["status"] == "awaiting_user"
    assert captured["entity_type"] == "ingresos"


def test_run_agent_returns_503_without_api_key(monkeypatch) -> None:
    fake_session = SimpleNamespace(id=7, state_json={})

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)
    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    db = _fake_db()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/onboarding/7/run-agent")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_resolve_persists_user_mapping(monkeypatch) -> None:
    fake_session = SimpleNamespace(
        id=11,
        original_filename="gastos.xlsx",
        status="awaiting_user",
        entity_type="gastos",
        error_message=None,
        raw_file=None,
        state_json={
            "headers": ["Fecha", "Concepto", "Importe", "Notas"],
            "sample_rows": [],
            "entity_type": "gastos",
            "proposed_mapping": [],
        },
    )
    captured: dict = {}

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    async def fake_update(_db, session, **kwargs):
        captured.update(kwargs)
        return session

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)
    monkeypatch.setattr(onboarding_service, "update_session_state", fake_update)

    db = _fake_db()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/onboarding/11/resolve",
            data={
                "entity_type": "gastos",
                "target__Fecha": "fecha",
                "target__Concepto": "concepto",
                "target__Importe": "cantidad",
                "target__Notas": "IGNORE",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert captured["status"] == "previewing"
    assert captured["entity_type"] == "gastos"
    resolved = captured["state"]["resolved_mapping"]
    assert {r["source_column"]: r["target_field"] for r in resolved} == {
        "Fecha": "fecha",
        "Concepto": "concepto",
        "Importe": "cantidad",
        "Notas": "IGNORE",
    }


def test_confirm_runs_importer(monkeypatch) -> None:
    fake_session = SimpleNamespace(
        id=22,
        original_filename="gastos.xlsx",
        status="previewing",
        entity_type="gastos",
        error_message=None,
        state_json={
            "csv_output": "14/11/2025;Pienso;Coop;;21\n",
            "entity_type": "gastos",
        },
    )
    captured: dict = {}

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    async def fake_update(_db, session, **kwargs):
        captured.update(kwargs)
        return session

    async def fake_import(_db, content, tenant_id):
        captured["import_tenant_id"] = tenant_id
        captured["import_payload"] = content
        return [object(), object()], ["aviso de prueba"]

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)
    monkeypatch.setattr(onboarding_service, "update_session_state", fake_update)
    monkeypatch.setattr("app.routers.onboarding.import_expenses_csv", fake_import)

    db = _fake_db()
    db.rollback = AsyncMock()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/onboarding/22/confirm", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert captured["status"] == "imported"
    assert captured["state"]["imported_count"] == 2
    assert captured["import_tenant_id"] == 42


def _read_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_resolve_flags_missing_plot_per_sheet(monkeypatch) -> None:
    """Sheets whose inferred plot doesn't exist must yield validation errors."""
    fake_session = SimpleNamespace(
        id=55,
        original_filename="ingresos.xlsx",
        status="awaiting_user",
        entity_type="ingresos",
        error_message=None,
        raw_file=_read_fixture("ingresos_multi_sheet.xlsx"),
        state_json={
            "headers": ["Fecha", "Cliente", "Kg", "€/kg", "Importe"],
            "sample_rows": [],
            "entity_type": "ingresos",
            "parsed_sheets": [
                {
                    "sheet_name": "Ingresos CERRELLAR 25-26",
                    "headers": ["Fecha", "Cliente", "Kg", "€/kg", "Importe"],
                    "header_row_index": 1,
                    "sample_rows": [],
                    "total_data_rows": 2,
                    "inferred_plot_name": "Cerrellar",
                    "inferred_campaign_year": 2025,
                    "inferred_campaign_label": "2025/26",
                },
                {
                    "sheet_name": "Ingresos CERRELLAR 24-25",
                    "headers": ["Fecha", "Cliente", "Kg", "€/kg", "Importe"],
                    "header_row_index": 1,
                    "sample_rows": [],
                    "total_data_rows": 3,
                    "inferred_plot_name": "Cerrellar",
                    "inferred_campaign_year": 2024,
                    "inferred_campaign_label": "2024/25",
                },
            ],
        },
    )
    captured: dict = {}

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    async def fake_update(_db, session, **kwargs):
        captured.update(kwargs)
        return session

    async def fake_list_plots(_db, _tenant_id):
        # Tenant only has "Loma Alta" — "Cerrellar" is missing.
        return [SimpleNamespace(name="Loma Alta")]

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)
    monkeypatch.setattr(onboarding_service, "update_session_state", fake_update)
    monkeypatch.setattr("app.routers.onboarding.list_plots", fake_list_plots)

    db = _fake_db()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/onboarding/55/resolve",
            data={
                "entity_type": "ingresos",
                "target__Fecha": "fecha",
                "target__Cliente": "IGNORE",
                "target__Kg": "kg",
                "target__€/kg": "euros_kg",
                "target__Importe": "IGNORE",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    state = captured["state"]
    assert state["missing_plots"] == ["Cerrellar"]
    # No rows are transformed because all sheets reference the missing plot.
    assert state["csv_output"] == ""
    assert state["transformed_rows"] == 0
    # One validation error per affected sheet.
    sheet_errors = [
        e
        for e in state["validation_errors"]
        if e.get("column") == "bancal" and "no existe" in e.get("message", "")
    ]
    assert {e["sheet"] for e in sheet_errors} == {
        "Ingresos CERRELLAR 25-26",
        "Ingresos CERRELLAR 24-25",
    }


def test_resolve_accepts_existing_plot_case_insensitive(monkeypatch) -> None:
    """When the inferred plot exists (any case) the sheet is transformed."""
    fake_session = SimpleNamespace(
        id=56,
        original_filename="ingresos.xlsx",
        status="awaiting_user",
        entity_type="ingresos",
        error_message=None,
        raw_file=_read_fixture("ingresos_multi_sheet.xlsx"),
        state_json={
            "headers": ["Fecha", "Cliente", "Kg", "€/kg", "Importe"],
            "sample_rows": [],
            "entity_type": "ingresos",
            "parsed_sheets": [
                {
                    "sheet_name": "Ingresos CERRELLAR 25-26",
                    "headers": ["Fecha", "Cliente", "Kg", "€/kg", "Importe"],
                    "header_row_index": 1,
                    "sample_rows": [],
                    "total_data_rows": 2,
                    "inferred_plot_name": "Cerrellar",
                    "inferred_campaign_year": 2025,
                    "inferred_campaign_label": "2025/26",
                },
            ],
        },
    )
    captured: dict = {}

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    async def fake_update(_db, session, **kwargs):
        captured.update(kwargs)
        return session

    async def fake_list_plots(_db, _tenant_id):
        return [SimpleNamespace(name="CERRELLAR")]  # case differs intentionally

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)
    monkeypatch.setattr(onboarding_service, "update_session_state", fake_update)
    monkeypatch.setattr("app.routers.onboarding.list_plots", fake_list_plots)

    db = _fake_db()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post(
            "/onboarding/56/resolve",
            data={
                "entity_type": "ingresos",
                "target__Fecha": "fecha",
                "target__Cliente": "IGNORE",
                "target__Kg": "kg",
                "target__€/kg": "euros_kg",
                "target__Importe": "IGNORE",
            },
            follow_redirects=False,
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    state = captured["state"]
    assert state["missing_plots"] == []
    assert state["transformed_rows"] == 2
    assert "Cerrellar" in state["csv_output"]


def test_confirm_blocks_when_missing_plots(monkeypatch) -> None:
    fake_session = SimpleNamespace(
        id=57,
        original_filename="ingresos.xlsx",
        status="previewing",
        entity_type="ingresos",
        error_message=None,
        state_json={
            "csv_output": "01/12/2025;Cerrellar;1,2;;\n",
            "entity_type": "ingresos",
            "missing_plots": ["Cerrellar"],
        },
    )

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)

    db = _fake_db()
    app.dependency_overrides[require_write_access] = _override_user
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/onboarding/57/confirm", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 400
    assert "Cerrellar" in response.text


def test_upload_blocks_when_quota_exceeded(monkeypatch) -> None:
    async def fake_list(_db, *, tenant_id, limit=50):
        return []

    async def fake_full(_db, *, tenant_id, now=None):
        return 3  # trial limit

    monkeypatch.setattr(onboarding_service, "list_sessions", fake_list)
    monkeypatch.setattr(onboarding_service, "count_sessions_this_month", fake_full)

    db = _fake_db()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        with (FIXTURES / "gastos_cabeceras_irregulares.xlsx").open("rb") as fh:
            response = client.post(
                "/onboarding/upload",
                files={
                    "file": (
                        "gastos.xlsx",
                        fh,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                },
                follow_redirects=False,
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"].startswith("/onboarding/?msg=")
    assert "msg_type=warning" in response.headers["location"]


def test_request_help_sends_email_and_marks_state(monkeypatch) -> None:
    fake_session = SimpleNamespace(
        id=42,
        tenant_id=42,
        state_json={},
        original_filename="x.xlsx",
        status="error",
        entity_type=None,
        error_message=None,
    )

    captured_update: dict = {}
    captured_email: dict = {}

    async def fake_get_session(_db, _id, tenant_id):
        return fake_session

    async def fake_update(_db, session, **kwargs):
        captured_update.update(kwargs)
        if "state" in kwargs:
            session.state_json = kwargs["state"]
        return session

    async def fake_send_email(to, subject, html_body, **kwargs):
        captured_email["to"] = to
        captured_email["subject"] = subject
        captured_email["html"] = html_body
        return True

    monkeypatch.setattr(onboarding_service, "get_session", fake_get_session)
    monkeypatch.setattr(onboarding_service, "update_session_state", fake_update)
    monkeypatch.setattr("app.routers.onboarding.send_email", fake_send_email)
    monkeypatch.setattr(settings, "CONTACT_EMAIL", "soporte@example.com")

    db = _fake_db()
    app.dependency_overrides[get_db] = lambda: db
    try:
        client = TestClient(app)
        response = client.post("/onboarding/42/request-help", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 303
    assert response.headers["location"] == "/onboarding/42"
    assert captured_email["to"] == "soporte@example.com"
    assert "42" in captured_email["subject"] or "x.xlsx" in captured_email["html"]
    assert "help_requested_at" in captured_update["state"]

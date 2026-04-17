from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.auth import require_user
from app.database import get_db
from app.main import app


def _override_user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True)


def _build_fake_db() -> SimpleNamespace:
    return SimpleNamespace(commit=AsyncMock())


def test_app_registers_import_routes() -> None:
    paths = {route.path for route in app.routes}

    assert "/import/" in paths
    assert "/import/expenses" in paths
    assert "/import/incomes" in paths
    assert "/import/plots" in paths
    assert "/import/all.zip" in paths
    assert "/import/irrigation" in paths
    assert "/import/wells" in paths
    assert "/import/truffles" in paths


def test_import_page_renders() -> None:
    fake_db = _build_fake_db()
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        client = TestClient(app)
        response = client.get("/import/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importar datos CSV" in response.text
    assert "Riego" in response.text
    assert "Pozos" in response.text


def test_upload_irrigation_renders_result(monkeypatch) -> None:
    fake_db = _build_fake_db()

    async def fake_import_irrigation_csv(db, content: bytes, user_id: int):
        return [object(), object()], ["aviso de prueba"]

    monkeypatch.setattr(
        "app.routers.imports.import_irrigation_csv",
        fake_import_irrigation_csv,
    )
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        client = TestClient(app)
        response = client.post(
            "/import/irrigation",
            files={"file": ("riego.csv", b"15/06/2025;Bancal Sur;10,500", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importación de riego completada" in response.text
    assert "aviso de prueba" in response.text
    fake_db.commit.assert_awaited_once()


def test_upload_wells_renders_result(monkeypatch) -> None:
    fake_db = _build_fake_db()

    async def fake_import_wells_csv(db, content: bytes, user_id: int):
        return [object(), object()], ["aviso de prueba"]

    monkeypatch.setattr(
        "app.routers.imports.import_wells_csv",
        fake_import_wells_csv,
    )
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        client = TestClient(app)
        response = client.post(
            "/import/wells",
            files={"file": ("pozos.csv", b"15/06/2025;Bancal Sur;5", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importación de pozos completada" in response.text
    assert "aviso de prueba" in response.text
    fake_db.commit.assert_awaited_once()


def test_upload_expenses_renders_result(monkeypatch) -> None:
    fake_db = _build_fake_db()

    async def fake_import_expenses_csv(db, content: bytes, user_id: int):
        return [object(), object(), object()], ["gasto no asignado"]

    monkeypatch.setattr(
        "app.routers.imports.import_expenses_csv",
        fake_import_expenses_csv,
    )
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        client = TestClient(app)
        response = client.post(
            "/import/expenses",
            files={"file": ("gastos.csv", b"15/06/2025;Poda;Javi;10,5", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importación de gastos completada" in response.text
    assert "gasto no asignado" in response.text
    fake_db.commit.assert_awaited_once()


def test_upload_incomes_renders_result(monkeypatch) -> None:
    fake_db = _build_fake_db()

    async def fake_import_incomes_csv(db, content: bytes, user_id: int):
        return [object()], []

    monkeypatch.setattr(
        "app.routers.imports.import_incomes_csv",
        fake_import_incomes_csv,
    )
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        client = TestClient(app)
        response = client.post(
            "/import/incomes",
            files={"file": ("ingresos.csv", b"15/06/2025;Venta;2,5;100", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importación de ingresos completada" in response.text
    fake_db.commit.assert_awaited_once()


def test_upload_plots_renders_result(monkeypatch) -> None:
    fake_db = _build_fake_db()

    async def fake_import_plots_csv(db, content: bytes, user_id: int):
        return [object()], []

    monkeypatch.setattr(
        "app.routers.imports.import_plots_csv",
        fake_import_plots_csv,
    )
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        client = TestClient(app)
        response = client.post(
            "/import/plots",
            files={"file": ("parcelas.csv", b"Bancal Sur;01/01/2020", "text/csv")},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importación de parcelas completada" in response.text
    fake_db.commit.assert_awaited_once()


def test_upload_truffles_renders_result(monkeypatch) -> None:
    fake_db = _build_fake_db()

    async def fake_import_truffles_csv(db, content: bytes, user_id: int):
        return [object(), object()], ["evento omitido"]

    monkeypatch.setattr(
        "app.routers.imports.import_truffles_csv",
        fake_import_truffles_csv,
    )
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        client = TestClient(app)
        response = client.post(
            "/import/truffles",
            files={
                "file": (
                    "produccion.csv",
                    b"10/12/2025 08:15:00;Bancal Sur;A3;45,5;manual",
                    "text/csv",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importación de producción completada" in response.text
    assert "evento omitido" in response.text
    fake_db.commit.assert_awaited_once()


def test_upload_all_zip_renders_result(monkeypatch) -> None:
    fake_db = _build_fake_db()

    async def fake_import_all_csv_zip(db, content: bytes, user_id: int):
        return {"parcelas.csv": 2, "gastos.csv": 1}, ["gastos.csv: aviso de prueba"]

    monkeypatch.setattr(
        "app.routers.imports.import_all_csv_zip",
        fake_import_all_csv_zip,
    )
    app.dependency_overrides[require_user] = _override_user
    app.dependency_overrides[get_db] = lambda: fake_db

    try:
        client = TestClient(app)
        response = client.post(
            "/import/all.zip",
            files={
                "file": (
                    "importacion.zip",
                    b"PK\x03\x04dummy",
                    "application/zip",
                )
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Importación de ZIP completada" in response.text
    assert "gastos.csv: aviso de prueba" in response.text
    assert "parcelas: 2" in response.text
    fake_db.commit.assert_awaited_once()

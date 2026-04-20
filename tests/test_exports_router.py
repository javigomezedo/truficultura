from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.auth import require_user
from app.database import get_db
from app.main import app


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True)


def _db() -> SimpleNamespace:
    return SimpleNamespace()


def test_export_page_renders() -> None:
    app.dependency_overrides[require_user] = _user
    try:
        client = TestClient(app)
        response = client.get("/export/")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert "Exportar datos CSV" in response.text


def test_download_plots_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_plots_csv", AsyncMock(return_value=b"plots")
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/plots.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"plots"
    assert (
        response.headers["content-disposition"] == "attachment; filename=parcelas.csv"
    )


def test_download_expenses_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_expenses_csv", AsyncMock(return_value=b"expenses")
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/expenses.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"expenses"
    assert response.headers["content-disposition"] == "attachment; filename=gastos.csv"


def test_download_incomes_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_incomes_csv", AsyncMock(return_value=b"incomes")
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/incomes.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"incomes"
    assert (
        response.headers["content-disposition"] == "attachment; filename=ingresos.csv"
    )


def test_download_irrigation_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_irrigation_csv",
        AsyncMock(return_value=b"irrigation"),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/irrigation.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"irrigation"
    assert response.headers["content-disposition"] == "attachment; filename=riego.csv"


def test_download_truffles_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_truffles_csv",
        AsyncMock(return_value=b"truffles"),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/truffles.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"truffles"
    assert (
        response.headers["content-disposition"] == "attachment; filename=produccion.csv"
    )


def test_download_recurring_expenses_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_recurring_expenses_csv",
        AsyncMock(return_value=b"recurrentes"),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/recurring_expenses.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"recurrentes"
    assert (
        response.headers["content-disposition"]
        == "attachment; filename=gastos_recurrentes.csv"
    )


def test_download_all_csv_zip(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_all_csv_zip",
        AsyncMock(return_value=b"zip-content"),
    )
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/all.zip")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"zip-content"
    assert (
        response.headers["content-disposition"]
        == "attachment; filename=exportacion_csv.zip"
    )

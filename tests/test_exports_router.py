from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from app.auth import require_subscription
from app.database import get_db
from app.main import app


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True, active_tenant_id=1)


def _db() -> SimpleNamespace:
    return SimpleNamespace()


def test_export_page_renders() -> None:
    app.dependency_overrides[require_subscription] = _user
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
    app.dependency_overrides[require_subscription] = _user
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
    app.dependency_overrides[require_subscription] = _user
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
    app.dependency_overrides[require_subscription] = _user
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
    app.dependency_overrides[require_subscription] = _user
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
    app.dependency_overrides[require_subscription] = _user
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
    app.dependency_overrides[require_subscription] = _user
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
    app.dependency_overrides[require_subscription] = _user
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


def test_download_wells_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_wells_csv", AsyncMock(return_value=b"wells")
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/wells.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"wells"
    assert response.headers["content-disposition"] == "attachment; filename=pozos.csv"


def test_download_plot_events_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_plot_events_csv",
        AsyncMock(return_value=b"labores"),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/plot_events.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"labores"
    assert response.headers["content-disposition"] == "attachment; filename=labores.csv"


def test_download_harvests_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_harvests_csv",
        AsyncMock(return_value=b"cosechas"),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/harvests.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"cosechas"
    assert (
        response.headers["content-disposition"] == "attachment; filename=cosechas.csv"
    )


def test_download_presences_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_presences_csv",
        AsyncMock(return_value=b"presencias"),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/presences.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"presencias"
    assert (
        response.headers["content-disposition"] == "attachment; filename=presencias.csv"
    )


def test_download_plants_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_plants_csv",
        AsyncMock(return_value=b"plantas"),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/plants.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"plantas"
    assert response.headers["content-disposition"] == "attachment; filename=plantas.csv"


def test_download_brule_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_brule_csv", AsyncMock(return_value=b"brule")
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/brule.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"brule"
    assert response.headers["content-disposition"] == "attachment; filename=brule.csv"


def test_download_rainfall_csv(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.exports.export_rainfall_csv",
        AsyncMock(return_value=b"lluvia"),
    )
    app.dependency_overrides[require_subscription] = _user
    app.dependency_overrides[get_db] = _db
    try:
        client = TestClient(app)
        response = client.get("/export/rainfall.csv")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.content == b"lluvia"
    assert response.headers["content-disposition"] == "attachment; filename=lluvia.csv"

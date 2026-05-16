"""Tests para el router de ayuda pública (/ayuda/...)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from app.auth import require_user
from app.database import get_db
from app.main import app

client = TestClient(app)


def _user(**kwargs):
    defaults = dict(
        id=1,
        username="trufero",
        first_name="Juan",
        last_name="García",
        email="juan@example.com",
        role="user",
        is_active=True,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_help_index_returns_200_and_links_to_glossary():
    resp = client.get("/ayuda/")
    assert resp.status_code == 200
    body = resp.text
    assert "Glosario" in body
    assert "/ayuda/glosario" in body


def test_help_index_renders_faq_section():
    resp = client.get("/ayuda/")
    assert resp.status_code == 200
    body = resp.text
    assert 'id="faq"' in body
    # Algunas preguntas clave de la FAQ.
    assert "campaña" in body.lower()
    assert "reparten los gastos" in body
    assert "/ayuda/videos" in body


def test_videos_page_returns_200():
    resp = client.get("/ayuda/videos")
    assert resp.status_code == 200
    assert "Vídeos" in resp.text or "vídeo" in resp.text.lower()


def test_glossary_returns_200_and_contains_key_terms():
    resp = client.get("/ayuda/glosario")
    assert resp.status_code == 200
    body = resp.text
    for term in [
        "Brulé",
        "Campaña agrícola",
        "SIGPAC",
        "Prorrateo",
        "Porcentaje de parcela",
        "ROI",
    ]:
        assert term in body, f"Falta término en el glosario: {term}"


def test_help_endpoints_are_public_no_redirect_to_login():
    for path in ("/ayuda/", "/ayuda/glosario", "/ayuda/videos"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 200, f"{path} redirige o falla: {resp.status_code}"


def test_onboarding_guide_step_updates_user():
    user = _user()
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    try:
        local_client = TestClient(app)
        resp = local_client.post(
            "/ayuda/onboarding-guide/step",
            data={"step": "first_plot"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["ok"] is True
    assert payload["step"] == "first_plot"
    db.execute.assert_awaited()
    db.commit.assert_awaited()


def test_onboarding_guide_step_rejects_invalid_value():
    user = _user()
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()

    app.dependency_overrides[require_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    try:
        local_client = TestClient(app)
        resp = local_client.post(
            "/ayuda/onboarding-guide/step",
            data={"step": "bogus"},
        )
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 400
    db.execute.assert_not_called()


def test_onboarding_guide_step_requires_auth():
    local_client = TestClient(app, follow_redirects=False)
    resp = local_client.post(
        "/ayuda/onboarding-guide/step",
        data={"step": "done"},
    )
    assert resp.status_code in (302, 303, 401)

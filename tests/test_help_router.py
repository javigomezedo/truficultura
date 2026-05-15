"""Tests para el router de ayuda pública (/ayuda/...)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_help_index_returns_200_and_links_to_glossary():
    resp = client.get("/ayuda/")
    assert resp.status_code == 200
    body = resp.text
    assert "Glosario" in body
    assert "/ayuda/glosario" in body


def test_glossary_returns_200_and_contains_key_terms():
    resp = client.get("/ayuda/glosario")
    assert resp.status_code == 200
    body = resp.text
    # Términos clave que deben aparecer documentados.
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
    """Los endpoints de ayuda deben ser accesibles sin sesión iniciada."""
    for path in ("/ayuda/", "/ayuda/glosario"):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 200, f"{path} redirige o falla: {resp.status_code}"

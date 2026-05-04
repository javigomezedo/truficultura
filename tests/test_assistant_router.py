from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.auth import require_admin, require_user
from app.database import get_db
from app.main import app


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=1, role="user", is_active=True, active_tenant_id=1)


def _db() -> MagicMock:
    return MagicMock()


def test_chat_requires_authentication() -> None:
    client = TestClient(app, follow_redirects=False)
    response = client.post("/api/assistant/chat", json={"message": "Hola"})
    assert response.status_code == 303
    assert "/login" in response.headers["location"]


def test_chat_returns_response_for_uso_intent(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.assistant.chat",
        AsyncMock(
            return_value={
                "response": "Desde el menú Parcelas, pulsa 'Nueva parcela'.",
                "intent": "uso",
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.assistant._get_adapter",
        MagicMock(return_value=MagicMock()),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/assistant/chat",
            json={"message": "¿Cómo doy de alta una parcela?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["response"] == "Desde el menú Parcelas, pulsa 'Nueva parcela'."
    assert data["intent"] == "uso"


def test_chat_returns_response_for_datos_intent(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.assistant.chat",
        AsyncMock(
            return_value={
                "response": "Tu campaña 2025/26 tuvo 5.000€ de rentabilidad.",
                "intent": "datos",
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.assistant._get_adapter",
        MagicMock(return_value=MagicMock()),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/assistant/chat",
            json={
                "message": "¿Cuál fue mi mejor campaña?",
                "history": [
                    {"role": "user", "content": "Hola"},
                    {"role": "assistant", "content": "¿En qué te ayudo?"},
                ],
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["intent"] == "datos"


def test_stream_requires_authentication() -> None:
    client = TestClient(app, follow_redirects=False)
    response = client.post("/api/assistant/stream", json={"message": "Hola"})
    assert response.status_code == 303
    assert "/login" in response.headers["location"]


def test_stream_returns_sse_payload(monkeypatch) -> None:
    async def fake_stream(messages):
        yield "Hola"
        yield " mundo"

    fake_adapter = MagicMock()
    fake_adapter.stream = fake_stream

    monkeypatch.setattr(
        "app.routers.assistant.prepare_chat_context",
        AsyncMock(
            return_value={
                "intent": "uso",
                "messages": [{"role": "system", "content": "ctx"}],
                "traceability": {
                    "retrieval_mode": "static",
                    "data_scope": "product-guidance",
                    "sources": ["kb:app_core_guidance"],
                },
            }
        ),
    )
    monkeypatch.setattr(
        "app.routers.assistant._get_adapter",
        MagicMock(return_value=fake_adapter),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post(
            "/api/assistant/stream",
            json={"message": "¿Cómo doy de alta una parcela?"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert '"type": "ready"' in response.text
    assert '"intent": "uso"' in response.text
    assert '"traceability"' in response.text
    assert '"type": "token"' in response.text
    assert '"type": "done"' in response.text


def test_stream_returns_503_when_api_key_missing(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post("/api/assistant/stream", json={"message": "Hola"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503


def test_chat_returns_503_when_api_key_missing(monkeypatch) -> None:
    from app.config import settings

    monkeypatch.setattr(settings, "OPENAI_API_KEY", None)

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post("/api/assistant/chat", json={"message": "Hola"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert "OPENAI_API_KEY" in response.json()["detail"]


def test_chat_rejects_empty_message() -> None:
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post("/api/assistant/chat", json={"message": ""})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_chat_rejects_message_over_1000_chars() -> None:
    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post("/api/assistant/chat", json={"message": "a" * 1001})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 422


def test_chat_returns_429_when_rate_limited(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.assistant._enforce_rate_limit",
        MagicMock(
            side_effect=HTTPException(status_code=429, detail="Límite alcanzado")
        ),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post("/api/assistant/chat", json={"message": "Hola"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 429


def test_stream_returns_429_when_rate_limited(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.routers.assistant._enforce_rate_limit",
        MagicMock(
            side_effect=HTTPException(status_code=429, detail="Límite alcanzado")
        ),
    )

    app.dependency_overrides[require_user] = _user
    app.dependency_overrides[get_db] = lambda: _db()
    try:
        client = TestClient(app)
        response = client.post("/api/assistant/stream", json={"message": "Hola"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 429


def test_metrics_requires_admin() -> None:
    client = TestClient(app, follow_redirects=False)
    response = client.get("/api/assistant/metrics")
    assert response.status_code == 303


def test_metrics_returns_snapshot_for_admin() -> None:
    app.dependency_overrides[require_admin] = _user
    try:
        client = TestClient(app)
        response = client.get("/api/assistant/metrics")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert "chat" in payload
    assert "stream" in payload
    assert "intents" in payload

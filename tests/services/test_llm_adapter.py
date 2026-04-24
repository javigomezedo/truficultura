from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.llm_adapter import OpenAIAdapter


@pytest.mark.asyncio
async def test_transcribe_returns_text() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"text": "Hola mundo"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_class:
        mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_class.return_value.__aexit__ = AsyncMock(return_value=False)

        adapter = OpenAIAdapter(api_key="test-key")
        text = await adapter.transcribe(b"audio data", "audio.webm", "audio/webm", language="es")

    assert text == "Hola mundo"
    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["data"]["model"] == "whisper-1"
    assert call_kwargs.kwargs["data"]["language"] == "es"


@pytest.mark.asyncio
async def test_transcribe_passes_language_from_caller() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"text": "Hello world"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_class:
        mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_class.return_value.__aexit__ = AsyncMock(return_value=False)

        adapter = OpenAIAdapter(api_key="test-key")
        await adapter.transcribe(b"audio data", "audio.webm", "audio/webm", language="en")

    call_kwargs = mock_client.post.call_args
    assert call_kwargs.kwargs["data"]["language"] == "en"


@pytest.mark.asyncio
async def test_transcribe_passes_filename_and_content_type() -> None:
    mock_response = MagicMock()
    mock_response.json.return_value = {"text": "test"}
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("httpx.AsyncClient") as mock_class:
        mock_class.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_class.return_value.__aexit__ = AsyncMock(return_value=False)

        adapter = OpenAIAdapter(api_key="test-key")
        await adapter.transcribe(b"data", "audio.ogg", "audio/ogg")

    call_kwargs = mock_client.post.call_args
    files = call_kwargs.kwargs["files"]
    filename, _data, content_type = files["file"]
    assert filename == "audio.ogg"
    assert content_type == "audio/ogg"

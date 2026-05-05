from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx

_OPENAI_CHAT_URL = "https://api.openai.com/v1/chat/completions"
_OPENAI_WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"
_DEFAULT_MODEL = "gpt-4o-mini"
_WHISPER_MODEL = "whisper-1"
_MAX_TOKENS = 800
_TEMPERATURE = 0.3
_AZURE_API_VERSION = "2024-10-21"


class LLMAdapter(ABC):
    """Abstract interface for LLM providers.

    Decouples router/service from vendor — swap OpenAI for Azure OpenAI or
    any other provider by subclassing without touching the service layer.
    """

    @abstractmethod
    async def complete(self, messages: list[dict]) -> str:
        """Return a full response string."""
        ...

    @abstractmethod
    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:
        """Yield response tokens as they arrive (used by SSE endpoint, Semana 2)."""
        ...


class OpenAIAdapter(LLMAdapter):
    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        self._api_key = api_key
        self._model = model

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def complete(self, messages: list[dict]) -> str:
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": _MAX_TOKENS,
            "temperature": _TEMPERATURE,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _OPENAI_CHAT_URL,
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:  # type: ignore[override]
        payload = {
            "model": self._model,
            "messages": messages,
            "max_tokens": _MAX_TOKENS,
            "temperature": _TEMPERATURE,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                _OPENAI_CHAT_URL,
                headers=self._headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        return
                    try:
                        data = json.loads(chunk)
                        choices = data.get("choices")
                        if not choices:
                            continue
                        delta = choices[0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str = "es",
    ) -> str:
        """Transcribe audio bytes using OpenAI Whisper API."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _OPENAI_WHISPER_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                files={"file": (filename, audio_bytes, content_type)},
                data={"model": _WHISPER_MODEL, "language": language},
            )
            resp.raise_for_status()
            data = resp.json()
            return data["text"]


class AzureOpenAIAdapter(LLMAdapter):
    """LLM adapter for Azure OpenAI Service.

    Data never leaves Microsoft's Azure infrastructure and is never used to
    train models. Compatible with the OpenAI API contract.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        deployment: str,
        whisper_deployment: str | None = None,
        whisper_endpoint: str | None = None,
        whisper_key: str | None = None,
    ) -> None:
        # Normalise endpoint: strip trailing slash
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._deployment = deployment
        self._whisper_deployment = whisper_deployment
        # Whisper puede estar en un recurso Azure distinto (diferente región/key)
        self._whisper_endpoint = (whisper_endpoint or endpoint).rstrip("/")
        self._whisper_key = whisper_key or api_key

    def _chat_url(self) -> str:
        return (
            f"{self._endpoint}/openai/deployments/{self._deployment}"
            f"/chat/completions?api-version={_AZURE_API_VERSION}"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "api-key": self._api_key,
            "Content-Type": "application/json",
        }

    async def complete(self, messages: list[dict]) -> str:
        payload = {
            "messages": messages,
            "max_tokens": _MAX_TOKENS,
            "temperature": _TEMPERATURE,
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                self._chat_url(),
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    async def stream(self, messages: list[dict]) -> AsyncIterator[str]:  # type: ignore[override]
        payload = {
            "messages": messages,
            "max_tokens": _MAX_TOKENS,
            "temperature": _TEMPERATURE,
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                self._chat_url(),
                headers=self._headers(),
                json=payload,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[6:]
                    if chunk.strip() == "[DONE]":
                        return
                    try:
                        data = json.loads(chunk)
                        choices = data.get("choices")
                        if not choices:
                            continue
                        delta = choices[0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (KeyError, IndexError, json.JSONDecodeError):
                        continue

    async def transcribe(
        self,
        audio_bytes: bytes,
        filename: str = "audio.webm",
        content_type: str = "audio/webm",
        language: str = "es",
    ) -> str:
        """Transcribe audio using Azure OpenAI Whisper deployment."""
        if not self._whisper_deployment:
            raise RuntimeError(
                "whisper_deployment not configured in AzureOpenAIAdapter"
            )
        url = (
            f"{self._whisper_endpoint}/openai/deployments/{self._whisper_deployment}"
            f"/audio/transcriptions?api-version={_AZURE_API_VERSION}"
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={"api-key": self._whisper_key},
                files={"file": (filename, audio_bytes, content_type)},
                data={"language": language},
            )
            resp.raise_for_status()
            return resp.json()["text"]

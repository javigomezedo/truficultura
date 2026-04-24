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
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (KeyError, json.JSONDecodeError):
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

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.assistant import AssistantRequest, AssistantResponse
from app.services.assistant_service import chat, prepare_chat_context
from app.services.llm_adapter import OpenAIAdapter

router = APIRouter(prefix="/api/assistant", tags=["assistant"])
logger = logging.getLogger(__name__)

_RATE_LIMIT_KEY = "assistant_rate_timestamps"
_RATE_LIMIT_MAX_REQUESTS = 20
_RATE_LIMIT_WINDOW_SECONDS = 300


def _get_adapter() -> OpenAIAdapter:
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Asistente no disponible: configura OPENAI_API_KEY en el servidor.",
        )
    return OpenAIAdapter(api_key=settings.OPENAI_API_KEY)


def _enforce_rate_limit(request: Request) -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(seconds=_RATE_LIMIT_WINDOW_SECONDS)
    raw_items = request.session.get(_RATE_LIMIT_KEY, [])
    recent = []
    for value in raw_items:
        try:
            ts = datetime.fromisoformat(value)
        except ValueError:
            continue
        if ts >= cutoff:
            recent.append(ts)

    if len(recent) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Has superado el límite temporal de consultas al asistente."
            " Inténtalo de nuevo en unos minutos.",
        )

    recent.append(now)
    request.session[_RATE_LIMIT_KEY] = [ts.isoformat() for ts in recent]


@router.post("/chat", response_model=AssistantResponse)
async def assistant_chat(
    body: AssistantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
) -> AssistantResponse:
    _enforce_rate_limit(request)
    started = perf_counter()
    adapter = _get_adapter()
    result = await chat(
        db=db,
        user_id=current_user.id,
        message=body.message,
        history=[m.model_dump() for m in body.history],
        adapter=adapter,
    )
    latency_ms = (perf_counter() - started) * 1000
    logger.info(
        "assistant.chat user_id=%s intent=%s latency_ms=%.1f response_chars=%s",
        current_user.id,
        result.get("intent"),
        latency_ms,
        len(result.get("response", "")),
    )
    return AssistantResponse(**result)


@router.post("/stream")
async def assistant_stream(
    body: AssistantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
) -> StreamingResponse:
    _enforce_rate_limit(request)
    started = perf_counter()
    adapter = _get_adapter()
    context = await prepare_chat_context(
        db=db,
        user_id=current_user.id,
        message=body.message,
        history=[m.model_dump() for m in body.history],
    )

    async def event_generator():
        streamed_chars = 0
        try:
            yield f"data: {json.dumps({'type': 'ready', 'intent': context['intent']})}\n\n"
            async for delta in adapter.stream(context["messages"]):
                streamed_chars += len(delta)
                yield f"data: {json.dumps({'type': 'token', 'delta': delta})}\n\n"
            yield 'data: {"type": "done"}\n\n'
            latency_ms = (perf_counter() - started) * 1000
            logger.info(
                "assistant.stream user_id=%s intent=%s latency_ms=%.1f streamed_chars=%s",
                current_user.id,
                context.get("intent"),
                latency_ms,
                streamed_chars,
            )
        except Exception:
            latency_ms = (perf_counter() - started) * 1000
            logger.warning(
                "assistant.stream.error user_id=%s intent=%s latency_ms=%.1f",
                current_user.id,
                context.get("intent"),
                latency_ms,
            )
            yield (
                "data: "
                '{"type":"error","message":"No se pudo completar la respuesta."}'
                "\n\n"
            )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )

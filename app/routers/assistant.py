from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from time import perf_counter

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_admin, require_user
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
_METRICS = {
    "chat": {"requests": 0, "errors": 0, "latency_ms_total": 0.0},
    "stream": {"requests": 0, "errors": 0, "latency_ms_total": 0.0},
    "intents": {"uso": 0, "datos": 0},
}


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


def _track_metrics(
    endpoint: str, intent: str | None, latency_ms: float, error: bool
) -> None:
    bucket = _METRICS.get(endpoint)
    if not bucket:
        return
    bucket["requests"] += 1
    bucket["latency_ms_total"] += latency_ms
    if error:
        bucket["errors"] += 1
    if intent in _METRICS["intents"]:
        _METRICS["intents"][intent] += 1


@router.get("/metrics")
async def assistant_metrics(current_user: User = Depends(require_admin)) -> dict:
    chat_requests = _METRICS["chat"]["requests"]
    stream_requests = _METRICS["stream"]["requests"]
    return {
        "chat": {
            **_METRICS["chat"],
            "avg_latency_ms": (
                _METRICS["chat"]["latency_ms_total"] / chat_requests
                if chat_requests
                else 0.0
            ),
        },
        "stream": {
            **_METRICS["stream"],
            "avg_latency_ms": (
                _METRICS["stream"]["latency_ms_total"] / stream_requests
                if stream_requests
                else 0.0
            ),
        },
        "intents": _METRICS["intents"],
    }


@router.post("/chat", response_model=AssistantResponse)
async def assistant_chat(
    body: AssistantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
) -> AssistantResponse:
    _enforce_rate_limit(request)
    started = perf_counter()
    intent = None
    has_error = False
    adapter = _get_adapter()
    try:
        result = await chat(
            db=db,
            user_id=current_user.id,
            message=body.message,
            history=[m.model_dump() for m in body.history],
            adapter=adapter,
        )
        intent = result.get("intent")
        latency_ms = (perf_counter() - started) * 1000
        logger.info(
            "assistant.chat user_id=%s intent=%s latency_ms=%.1f response_chars=%s",
            current_user.id,
            intent,
            latency_ms,
            len(result.get("response", "")),
        )
        return AssistantResponse(**result)
    except Exception:
        has_error = True
        raise
    finally:
        latency_ms = (perf_counter() - started) * 1000
        _track_metrics("chat", intent, latency_ms, has_error)


@router.post("/stream")
async def assistant_stream(
    body: AssistantRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
) -> StreamingResponse:
    _enforce_rate_limit(request)
    started = perf_counter()
    has_error = False
    adapter = _get_adapter()
    context = await prepare_chat_context(
        db=db,
        user_id=current_user.id,
        message=body.message,
        history=[m.model_dump() for m in body.history],
    )

    async def event_generator():
        nonlocal has_error
        streamed_chars = 0
        try:
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "ready",
                        "intent": context["intent"],
                        "traceability": context.get("traceability"),
                    }
                )
                + "\n\n"
            )
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
            has_error = True
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
        finally:
            latency_ms = (perf_counter() - started) * 1000
            _track_metrics("stream", context.get("intent"), latency_ms, has_error)

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

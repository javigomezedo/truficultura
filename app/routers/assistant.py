from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
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


def _get_adapter() -> OpenAIAdapter:
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Asistente no disponible: configura OPENAI_API_KEY en el servidor.",
        )
    return OpenAIAdapter(api_key=settings.OPENAI_API_KEY)


@router.post("/chat", response_model=AssistantResponse)
async def assistant_chat(
    body: AssistantRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
) -> AssistantResponse:
    adapter = _get_adapter()
    result = await chat(
        db=db,
        user_id=current_user.id,
        message=body.message,
        history=[m.model_dump() for m in body.history],
        adapter=adapter,
    )
    return AssistantResponse(**result)


@router.post("/stream")
async def assistant_stream(
    body: AssistantRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_user),
) -> StreamingResponse:
    adapter = _get_adapter()
    context = await prepare_chat_context(
        db=db,
        user_id=current_user.id,
        message=body.message,
        history=[m.model_dump() for m in body.history],
    )

    async def event_generator():
        try:
            yield f"data: {json.dumps({'type': 'ready', 'intent': context['intent']})}\n\n"
            async for delta in adapter.stream(context["messages"]):
                yield f"data: {json.dumps({'type': 'token', 'delta': delta})}\n\n"
            yield 'data: {"type": "done"}\n\n'
        except Exception:
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

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import require_user
from app.config import settings
from app.database import get_db
from app.models.user import User
from app.schemas.assistant import AssistantRequest, AssistantResponse
from app.services.assistant_service import chat
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

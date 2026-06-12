from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import config
from ai.chat import AIAvailabilityError, AIRuntimeError, call_deepseek


router = APIRouter()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    history: List[ChatMessage] = Field(default_factory=list)
    message: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    available: bool = True
    model: str


@router.get("/status")
async def ai_status() -> Dict[str, Any]:
    return {
        "available": config.is_ai_enabled(),
        "model": config.DEEPSEEK_MODEL,
    }


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(request: ChatRequest) -> ChatResponse:
    if not config.is_ai_enabled():
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set DEEPSEEK_API_KEY in backend/.env",
        )

    history = [{"role": m.role, "content": m.content} for m in request.history]

    try:
        reply = await call_deepseek(
            payload=request.payload,
            history=history,
            user_message=request.message,
        )
    except AIAvailabilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except AIRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return ChatResponse(message=reply, available=True, model=config.DEEPSEEK_MODEL)

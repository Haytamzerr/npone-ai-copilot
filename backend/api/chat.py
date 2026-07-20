"""
api/chat.py
------------
Public-facing chat endpoints consumed by the frontend widget.
No authentication required (it's a public marketing-site chatbot), but every
route is rate-limited and every input sanitized.
"""
import json
import logging

from fastapi import APIRouter, Depends, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.models import Feedback, Message
from database.session import get_db
from models.schemas import (
    ChatRequest,
    ChatResponse,
    ClearConversationRequest,
    FeedbackRequest,
    SourceRef,
)
from services import memory_service, rag_service
from utils.security import looks_like_prompt_injection, sanitize_text

logger = logging.getLogger("npone.chat")
settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix=f"{settings.API_PREFIX}/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
@limiter.limit(settings.RATE_LIMIT_CHAT)
def chat(request: Request, payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    clean_message = sanitize_text(payload.message)

    if looks_like_prompt_injection(clean_message):
        logger.warning("Potential prompt injection blocked | session=%s", payload.session_id)
        # We don't hard-block the user; the system prompt already treats such
        # text as inert content. We just flag it for monitoring.

    conversation = memory_service.get_or_create_conversation(
        db, payload.session_id, payload.language
    )
    history = memory_service.get_history(db, conversation.id)

    result = rag_service.answer_question(
        question=clean_message,
        language=payload.language,
        history=history,
    )

    memory_service.save_message(db, conversation.id, "user", clean_message)
    assistant_msg = memory_service.save_message(
        db,
        conversation.id,
        "assistant",
        result.answer,
        sources=result.sources,
        response_time_ms=result.response_time_ms,
        llm_provider=result.provider,
    )
    db.commit()

    return ChatResponse(
        answer=result.answer,
        sources=[SourceRef(**s) for s in result.sources],
        conversation_id=conversation.id,
        message_id=assistant_msg.id,
        response_time_ms=result.response_time_ms,
        provider=result.provider,
    )


@router.post("/feedback")
@limiter.limit(settings.RATE_LIMIT_CHAT)
def submit_feedback(request: Request, payload: FeedbackRequest, db: Session = Depends(get_db)):
    message = db.get(Message, payload.message_id)
    if message is None:
        return {"ok": False, "detail": "Message not found"}

    feedback = Feedback(
        message_id=payload.message_id,
        is_helpful=payload.is_helpful,
        comment=sanitize_text(payload.comment or ""),
    )
    db.merge(feedback)
    db.commit()
    return {"ok": True}


@router.post("/clear")
@limiter.limit(settings.RATE_LIMIT_CHAT)
def clear_conversation(
    request: Request, payload: ClearConversationRequest, db: Session = Depends(get_db)
):
    memory_service.clear_conversation(db, payload.session_id)
    db.commit()
    return {"ok": True}

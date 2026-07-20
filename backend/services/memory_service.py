"""
services/memory_service.py
-----------------------------
Persists and retrieves per-session conversation history from the database.

Design decision:
    Memory lives in SQL (Conversation/Message tables) rather than in an
    in-process dict or LangChain's in-memory ConversationBufferMemory. This
    is required because:
      - The API may run as multiple Uvicorn/Gunicorn workers behind Nginx;
        in-memory state would be inconsistent across workers.
      - The admin dashboard needs to query history for analytics (top
        questions, conversation counts) -- it must already be durable.
"""
import json
from typing import List, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Conversation, Message


def get_or_create_conversation(db: Session, session_id: str, language: str) -> Conversation:
    stmt = select(Conversation).where(Conversation.session_id == session_id).order_by(
        Conversation.created_at.desc()
    )
    conversation = db.execute(stmt).scalars().first()
    if conversation is None:
        conversation = Conversation(session_id=session_id, language=language)
        db.add(conversation)
        db.flush()
    return conversation


def get_history(db: Session, conversation_id: str) -> List[Tuple[str, str]]:
    stmt = (
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    messages = db.execute(stmt).scalars().all()
    return [(m.role, m.content) for m in messages]


def save_message(
    db: Session,
    conversation_id: str,
    role: str,
    content: str,
    sources: list | None = None,
    response_time_ms: int = 0,
    llm_provider: str = "",
) -> Message:
    message = Message(
        conversation_id=conversation_id,
        role=role,
        content=content,
        sources=json.dumps(sources or []),
        response_time_ms=response_time_ms,
        llm_provider=llm_provider,
    )
    db.add(message)
    db.flush()
    return message


def clear_conversation(db: Session, session_id: str) -> None:
    stmt = select(Conversation).where(Conversation.session_id == session_id)
    conversations = db.execute(stmt).scalars().all()
    for c in conversations:
        db.delete(c)

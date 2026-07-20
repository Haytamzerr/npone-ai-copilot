"""
api/admin.py
-------------
Authenticated admin endpoints powering the dashboard: login, aggregate
statistics, logs, and knowledge-base / vector-store status. Every route
(except /login) is protected by utils.deps.require_admin.
"""
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config.settings import get_settings
from database.models import Conversation, Feedback, KnowledgeDocument, Message, RequestLog
from database.session import get_db
from models.schemas import DashboardStats, LoginRequest, TokenResponse
from services.llm_service import get_llm_provider
from services.rag_service import reload_vectorstore
from utils.deps import require_admin
from utils.security import create_access_token, verify_password

settings = get_settings()
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix=f"{settings.API_PREFIX}/admin", tags=["admin"])


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.RATE_LIMIT_ADMIN)
def login(request: Request, payload: LoginRequest):
    valid_user = payload.username == settings.ADMIN_USERNAME
    valid_pass = bool(settings.ADMIN_PASSWORD_HASH) and verify_password(
        payload.password, settings.ADMIN_PASSWORD_HASH
    )
    if not (valid_user and valid_pass):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin credentials"
        )
    token = create_access_token(subject=payload.username)
    return TokenResponse(access_token=token)


@router.get("/stats", response_model=DashboardStats)
def stats(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    total_conversations = db.scalar(select(func.count(Conversation.id))) or 0
    total_messages = db.scalar(select(func.count(Message.id))) or 0
    avg_response_time = db.scalar(
        select(func.avg(Message.response_time_ms)).where(Message.role == "assistant")
    ) or 0.0

    user_messages = db.scalars(
        select(Message.content).where(Message.role == "user")
    ).all()
    top_counter = Counter(m.strip().lower() for m in user_messages)
    top_questions = [
        {"question": q, "count": c} for q, c in top_counter.most_common(10)
    ]

    positive = db.scalar(select(func.count(Feedback.id)).where(Feedback.is_helpful.is_(True))) or 0
    negative = db.scalar(select(func.count(Feedback.id)).where(Feedback.is_helpful.is_(False))) or 0

    kb_docs = db.scalar(select(func.count(KnowledgeDocument.id))) or 0
    kb_chunks = db.scalar(select(func.sum(KnowledgeDocument.chunk_count))) or 0

    return DashboardStats(
        total_conversations=total_conversations,
        total_messages=total_messages,
        avg_response_time_ms=round(float(avg_response_time), 2),
        top_questions=top_questions,
        feedback_positive=positive,
        feedback_negative=negative,
        knowledge_documents=kb_docs,
        vectorstore_chunks=int(kb_chunks),
        active_llm_provider=get_llm_provider().name,
    )


@router.get("/logs")
def logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    _admin: str = Depends(require_admin),
):
    rows = db.scalars(
        select(RequestLog).order_by(RequestLog.created_at.desc()).limit(limit)
    ).all()
    return [
        {
            "endpoint": r.endpoint,
            "status_code": r.status_code,
            "duration_ms": r.duration_ms,
            "error": r.error,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@router.get("/knowledge-base/status")
def knowledge_base_status(db: Session = Depends(get_db), _admin: str = Depends(require_admin)):
    index_path = Path(settings.VECTORSTORE_DIR)
    docs = db.scalars(select(KnowledgeDocument)).all()
    return {
        "vectorstore_exists": index_path.exists(),
        "vectorstore_path": str(index_path),
        "documents": [
            {
                "source": d.source_path,
                "url": d.source_url,
                "type": d.doc_type,
                "chunks": d.chunk_count,
                "indexed_at": d.indexed_at.isoformat(),
            }
            for d in docs
        ],
    }


@router.post("/knowledge-base/reload")
def reload_knowledge_base(_admin: str = Depends(require_admin)):
    """Hot-reloads the FAISS index after `ingestion/ingest.py` has run, with
    no need to restart the FastAPI process."""
    reload_vectorstore()
    return {"ok": True, "detail": "Vector store cache cleared and will reload on next query."}

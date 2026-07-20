"""
models/schemas.py
------------------
Pydantic v2 schemas: the API's public contract. Kept separate from the ORM
models (database/models.py) so the persistence layer can evolve without
breaking the API, and vice versa (Single Responsibility Principle).
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator


class SourceRef(BaseModel):
    title: str
    url: Optional[str] = None
    snippet: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: str = Field(..., min_length=8, max_length=64)
    language: Literal["en", "fr", "ar"] = "en"

    @field_validator("message")
    @classmethod
    def strip_and_check(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message cannot be empty")
        return v


class ChatResponse(BaseModel):
    answer: str
    sources: List[SourceRef] = []
    conversation_id: str
    message_id: str
    response_time_ms: int
    provider: str


class FeedbackRequest(BaseModel):
    message_id: str
    is_helpful: bool
    comment: Optional[str] = Field(default="", max_length=1000)


class ClearConversationRequest(BaseModel):
    session_id: str


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DashboardStats(BaseModel):
    total_conversations: int
    total_messages: int
    avg_response_time_ms: float
    top_questions: List[dict]
    feedback_positive: int
    feedback_negative: int
    knowledge_documents: int
    vectorstore_chunks: int
    active_llm_provider: str


class LogEntry(BaseModel):
    endpoint: str
    status_code: int
    duration_ms: int
    error: str
    created_at: datetime

    model_config = {"from_attributes": True}

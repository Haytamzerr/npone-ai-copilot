"""
services/rag_service.py
-------------------------
Orchestrates the full RAG pipeline:

    user question --> [condense w/ history] --> retriever (FAISS)
                   --> similarity-score gate --> prompt assembly
                   --> LLM (OpenAI or Ollama) --> answer + sources

Design decisions:
    - The FAISS index is loaded once (module-level singleton via lru_cache)
      and memory-mapped from disk; reloading it per-request would add
      hundreds of ms of latency per chat message.
    - We manually gate on MIN_SIMILARITY_SCORE instead of trusting the LLM to
      "say I don't know" -- LLMs are unreliable at self-assessing knowledge
      gaps, but a cosine-similarity threshold is deterministic and cheap.
    - Conversation memory is passed in per-session (see api/chat.py), keeping
      this service stateless and thread-safe -- state lives in the DB, not in
      a process-global dict, so it survives restarts and works with multiple
      backend workers.
"""
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Tuple

from langchain_community.vectorstores import FAISS
from langchain_core.messages import AIMessage, HumanMessage

from config.settings import get_settings
from prompts.system_prompt import SYSTEM_PROMPT_TEMPLATE
from services.embedding_service import get_embedding_model
from services.llm_service import get_llm_provider

settings = get_settings()


@dataclass
class RAGAnswer:
    answer: str
    sources: List[dict]
    provider: str
    response_time_ms: int


@lru_cache
def _load_vectorstore() -> FAISS:
    index_path = Path(settings.VECTORSTORE_DIR)
    if not index_path.exists():
        raise RuntimeError(
            f"Vector store not found at '{index_path}'. Run "
            f"`python ingestion/ingest.py` first to build the knowledge base index."
        )
    return FAISS.load_local(
        str(index_path),
        get_embedding_model(),
        allow_dangerous_deserialization=True,  # index is built by us, not user-supplied
    )


def reload_vectorstore() -> None:
    """Invalidate the cached index (called by admin dashboard after re-ingestion)."""
    _load_vectorstore.cache_clear()


def _format_history(history: List[Tuple[str, str]]) -> str:
    if not history:
        return "(no previous messages)"
    lines = []
    for role, content in history[-6:]:  # last 6 turns is enough context, keeps prompt small
        speaker = "User" if role == "user" else "Assistant"
        lines.append(f"{speaker}: {content}")
    return "\n".join(lines)


def answer_question(
    question: str,
    language: str,
    history: List[Tuple[str, str]] | None = None,
    provider_override: str | None = None,
) -> RAGAnswer:
    start = time.perf_counter()
    history = history or []

    vectorstore = _load_vectorstore()
    retriever_results = vectorstore.similarity_search_with_relevance_scores(
        question, k=settings.RETRIEVER_TOP_K
    )

    # Anti-hallucination gate: drop chunks below the relevance threshold.
    relevant = [
        (doc, score) for doc, score in retriever_results if score >= settings.MIN_SIMILARITY_SCORE
    ]

    if not relevant:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        return RAGAnswer(
            answer=settings.FALLBACK_MESSAGE,
            sources=[],
            provider="none",
            response_time_ms=elapsed_ms,
        )

    context = "\n\n---\n\n".join(
        f"[Source: {doc.metadata.get('title', 'N+ONE Datacenters')}]\n{doc.page_content}"
        for doc, _ in relevant
    )

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        language=language,
        context=context,
        chat_history=_format_history(history),
    )

    provider = get_llm_provider(provider_override)
    chat_model = provider.get_chat_model()

    messages = [
        ("system", system_prompt),
        ("human", question),
    ]
    response = chat_model.invoke(messages)
    answer_text = response.content if hasattr(response, "content") else str(response)

    sources = [
        {
            "title": doc.metadata.get("title", "N+ONE Datacenters"),
            "url": doc.metadata.get("source_url", ""),
            "snippet": doc.page_content[:220].strip() + "...",
        }
        for doc, _ in relevant
    ]
    # De-duplicate sources by title while preserving order.
    seen = set()
    unique_sources = []
    for s in sources:
        if s["title"] not in seen:
            seen.add(s["title"])
            unique_sources.append(s)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    return RAGAnswer(
        answer=answer_text,
        sources=unique_sources,
        provider=provider.name,
        response_time_ms=elapsed_ms,
    )

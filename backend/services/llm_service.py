"""
services/llm_service.py
------------------------
LLM provider abstraction (Strategy pattern).

Design decision:
    The internship spec requires the assistant to work with either a paid
    cloud LLM (OpenAI) or a self-hosted one (Ollama/Llama3/Mistral/Qwen), and
    to let an admin switch between them without touching the RAG pipeline.
    We express this as a small Protocol + two adapters instead of branching
    on `if provider == "openai"` throughout the codebase (Open/Closed
    Principle: adding a third provider, e.g. Anthropic, means adding one new
    adapter class, not editing existing ones).
"""
from abc import ABC, abstractmethod

from langchain_core.language_models.chat_models import BaseChatModel

from config.settings import get_settings

settings = get_settings()


class LLMProvider(ABC):
    """Common interface every concrete provider must implement."""

    name: str

    @abstractmethod
    def get_chat_model(self) -> BaseChatModel:
        """Return a LangChain-compatible chat model instance."""
        raise NotImplementedError


class OpenAIProvider(LLMProvider):
    name = "openai"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_openai import ChatOpenAI

        if not settings.OPENAI_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER=openai but OPENAI_API_KEY is not set. "
                "Set it in .env or switch LLM_PROVIDER=ollama."
            )
        return ChatOpenAI(
            model=settings.OPENAI_MODEL,
            api_key=settings.OPENAI_API_KEY,
            temperature=0.2,   # low temperature: factual, non-creative answers
            max_tokens=600,
            timeout=30,
        )


class OllamaProvider(LLMProvider):
    name = "ollama"

    def get_chat_model(self) -> BaseChatModel:
        from langchain_community.chat_models import ChatOllama

        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=0.2,
        )


_PROVIDERS: dict[str, LLMProvider] = {
    "openai": OpenAIProvider(),
    "ollama": OllamaProvider(),
}


def get_llm_provider(name: str | None = None) -> LLMProvider:
    """
    Resolve the active provider. `name` lets the admin dashboard preview a
    different provider ad hoc; default falls back to the configured one.
    """
    provider_name = name or settings.LLM_PROVIDER
    if provider_name not in _PROVIDERS:
        raise ValueError(f"Unknown LLM provider '{provider_name}'. Valid: {list(_PROVIDERS)}")
    return _PROVIDERS[provider_name]

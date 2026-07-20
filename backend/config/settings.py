"""
config/settings.py
-------------------
Centralized, typed application configuration.

Design decision:
    We use pydantic-settings so every configuration value is validated at
    startup (fail fast) instead of failing deep inside a request handler.
    All secrets/config live in environment variables (.env), never hardcoded,
    per 12-factor app principles and the project's security requirements.
"""
from functools import lru_cache
from typing import List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- App ---
    APP_NAME: str = "N+ONE AI Customer Copilot"
    APP_ENV: Literal["development", "production"] = "development"
    DEBUG: bool = True
    API_PREFIX: str = "/api/v1"

    # --- Security ---
    SECRET_KEY: str
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    # --- Rate limiting ---
    RATE_LIMIT_CHAT: str = "20/minute"
    RATE_LIMIT_ADMIN: str = "60/minute"

    # --- Database ---
    DATABASE_URL: str = "sqlite:///./database/npone_copilot.db"

    # --- LLM provider ---
    LLM_PROVIDER: Literal["openai", "ollama"] = "openai"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"

    # --- Embeddings / RAG ---
    EMBEDDING_MODEL: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    VECTORSTORE_DIR: str = "./vectorstore/faiss_index"
    CHUNK_SIZE: int = 800
    CHUNK_OVERLAP: int = 120
    RETRIEVER_TOP_K: int = 4
    MIN_SIMILARITY_SCORE: float = 0.35
    FALLBACK_MESSAGE: str = (
        "I don't have enough verified information to answer that yet. "
        "Please contact N+ONE DATACENTERS directly."
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> "Settings":
    """Cached singleton accessor so .env is parsed only once per process."""
    return Settings()

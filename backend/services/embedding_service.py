"""
services/embedding_service.py
------------------------------
Wraps Sentence-Transformers behind LangChain's Embeddings interface.

Design decision:
    We use a *multilingual* MiniLM model (paraphrase-multilingual-MiniLM-L12-v2)
    because N+ONE operates in Morocco/Senegal/Ivory Coast and the chatbot must
    support English, French, and Arabic queries against a knowledge base that
    is itself partly bilingual (EN/FR). A single multilingual embedding space
    lets a French question retrieve an English chunk correctly, which two
    separate monolingual indexes could not do without a translation step.
"""
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from config.settings import get_settings

settings = get_settings()


@lru_cache
def get_embedding_model() -> HuggingFaceEmbeddings:
    """
    Loaded once per process (model weights are large) and reused for every
    ingestion run and every query -- loading per-request would add ~1-2s
    latency to every chat message.
    """
    return HuggingFaceEmbeddings(
        model_name=settings.EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True},  # cosine similarity via dot-product
    )

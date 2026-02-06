"""Embedding helpers used by CPM builtins."""

from .cache import EmbeddingCache
from .client import EmbeddingClient, VALID_EMBEDDING_MODES
from .connector import HttpEmbeddingConnector
from .config import EmbeddingProviderConfig, EmbeddingsConfigService
from .openai import (
    OpenAIEmbeddingClient,
    OpenAIEmbeddingsHttpClient,
    normalize_embeddings,
    parse_openai_response,
    serialize_openai_request,
)
from .postprocess import l2_normalize
from .types import EmbedRequestIR, EmbedResponseIR

__all__ = [
    "EmbeddingCache",
    "EmbeddingClient",
    "VALID_EMBEDDING_MODES",
    "HttpEmbeddingConnector",
    "EmbeddingProviderConfig",
    "EmbeddingsConfigService",
    "EmbedRequestIR",
    "EmbedResponseIR",
    "OpenAIEmbeddingsHttpClient",
    "OpenAIEmbeddingClient",
    "serialize_openai_request",
    "parse_openai_response",
    "normalize_embeddings",
    "l2_normalize",
]

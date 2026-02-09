from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import requests

from .openai import OpenAIEmbeddingsHttpClient

VALID_EMBEDDING_MODES = ("http",)


def _normalize_mode(mode: str) -> str:
    normalized = str(mode).strip().lower()
    if normalized not in VALID_EMBEDDING_MODES:
        raise ValueError("embeddings.mode must be 'http'")
    return normalized


def _resolve_http_endpoint(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1/embeddings"):
        return root
    return f"{root}/v1/embeddings"


@dataclass(frozen=True)
class EmbeddingClient:
    """Embedding client for OpenAI-compatible HTTP endpoints."""

    base_url: str
    mode: str = "http"
    timeout_s: float | None = None
    max_retries: int = 2

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", _normalize_mode(self.mode))
        object.__setattr__(self, "base_url", self.base_url.rstrip("/"))

    @property
    def _http_endpoint(self) -> str:
        return _resolve_http_endpoint(self.base_url)

    def health(self) -> bool:
        try:
            response = requests.options(self._http_endpoint, timeout=2.0)
            return response.status_code < 500
        except Exception:
            return False

    def embed_texts(
        self,
        texts: Sequence[str],
        *,
        model_name: str,
        max_seq_length: int,
        normalize: bool,
        dtype: str,
        show_progress: bool,
    ) -> np.ndarray:
        del show_progress
        client = OpenAIEmbeddingsHttpClient(
            endpoint=self._http_endpoint,
            timeout=float(self.timeout_s) if self.timeout_s is not None else 10.0,
            max_retries=self.max_retries,
        )
        payload_texts = list(texts)

        def _embed_batch(items: list[str]) -> np.ndarray:
            response = client.embed_texts(
                items,
                model=model_name,
                hints={"normalize": bool(normalize)},
                extra={"max_seq_length": int(max_seq_length)},
                normalize=bool(normalize),
            )
            return np.asarray(response.vectors, dtype=np.float32)

        try:
            array = _embed_batch(payload_texts)
        except ValueError as exc:
            message = str(exc).lower()
            too_many_items = "too many input items" in message or "invalid_input" in message
            if not too_many_items or len(payload_texts) <= 1:
                raise

            batch_size = min(64, len(payload_texts))
            while True:
                pieces: list[np.ndarray] = []
                try:
                    for start in range(0, len(payload_texts), batch_size):
                        batch = payload_texts[start : start + batch_size]
                        pieces.append(_embed_batch(batch))
                    array = np.vstack(pieces) if pieces else np.zeros((0, 0), dtype=np.float32)
                    break
                except ValueError as inner_exc:
                    inner_message = str(inner_exc).lower()
                    too_many_items = "too many input items" in inner_message or "invalid_input" in inner_message
                    if not too_many_items or batch_size <= 1:
                        raise
                    batch_size = max(1, batch_size // 2)

        if dtype.lower() == "float16":
            return array.astype(np.float16)
        return array.astype(np.float32)

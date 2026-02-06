from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
import requests

from .openai import OpenAIEmbeddingsHttpClient

VALID_EMBEDDING_MODES = ("http", "legacy")


def _normalize_mode(mode: str) -> str:
    normalized = str(mode).strip().lower()
    if normalized not in VALID_EMBEDDING_MODES:
        raise ValueError("embeddings.mode must be one of: http, legacy")
    return normalized


def _resolve_http_endpoint(base_url: str) -> str:
    root = base_url.rstrip("/")
    if root.endswith("/v1/embeddings"):
        return root
    return f"{root}/v1/embeddings"


@dataclass(frozen=True)
class EmbeddingClient:
    """Embedding client with compatibility mode for legacy endpoints."""

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

    @property
    def _legacy_endpoint(self) -> str:
        return f"{self.base_url}/embed"

    def health(self) -> bool:
        try:
            if self.mode == "legacy":
                response = requests.get(f"{self.base_url}/health", timeout=2.0)
                return response.ok
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
        if self.mode == "legacy":
            payload = {
                "model": model_name,
                "texts": list(texts),
                "options": {
                    "max_seq_length": int(max_seq_length),
                    "normalize": bool(normalize),
                    "show_progress": bool(show_progress),
                },
            }
            response = requests.post(
                self._legacy_endpoint,
                json=payload,
                timeout=self.timeout_s,
            )
            response.raise_for_status()
            vectors = response.json()["vectors"]
            array = np.asarray(vectors, dtype=np.float32)
        else:
            client = OpenAIEmbeddingsHttpClient(
                endpoint=self._http_endpoint,
                timeout=float(self.timeout_s) if self.timeout_s is not None else 10.0,
                max_retries=self.max_retries,
            )
            response = client.embed_texts(
                list(texts),
                model=model_name,
                hints={"normalize": bool(normalize)},
                extra={"max_seq_length": int(max_seq_length)},
                normalize=bool(normalize),
            )
            array = np.asarray(response.vectors, dtype=np.float32)

        if dtype.lower() == "float16":
            return array.astype(np.float16)
        return array.astype(np.float32)

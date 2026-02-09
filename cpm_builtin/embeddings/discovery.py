from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from .config import EmbeddingProviderConfig


@dataclass(frozen=True)
class DiscoveryResult:
    provider: str
    fetched_at: float
    models: tuple[str, ...]
    dims: dict[str, int]
    source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "fetched_at": self.fetched_at,
            "models": list(self.models),
            "dims": dict(self.dims),
            "source": self.source,
        }


def load_cache(cache_path: Path) -> dict[str, Any]:
    if not cache_path.exists():
        return {}
    try:
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def save_cache(cache_path: Path, payload: dict[str, Any]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def refresh_provider_discovery(
    provider: EmbeddingProviderConfig,
    *,
    cache_path: Path,
    ttl_seconds: int | None,
    force: bool = False,
) -> DiscoveryResult:
    cache = load_cache(cache_path)
    entry = cache.get(provider.name) if isinstance(cache.get(provider.name), dict) else None

    now = time.time()
    if not force and entry and ttl_seconds and ttl_seconds > 0:
        fetched_at = float(entry.get("fetched_at") or 0.0)
        if now - fetched_at <= ttl_seconds:
            return _to_result(provider.name, entry)

    result = _discover(provider)
    cache[provider.name] = result.to_dict()
    save_cache(cache_path, cache)
    return result


def _discover(provider: EmbeddingProviderConfig) -> DiscoveryResult:
    base_url = provider.resolved_http_base_url
    headers = provider.resolved_headers_static
    timeout = provider.resolved_http_timeout or 10.0
    source = "probe"
    models: list[str] = []
    dims: dict[str, int] = {}

    models_url = f"{base_url}{provider.resolved_http_models_path}"
    try:
        response = requests.get(models_url, headers=headers, timeout=timeout)
        if response.ok:
            payload = response.json()
            models = _extract_models(payload)
            source = "models"
    except Exception:
        models = []

    probe_model = provider.resolved_hint_model or provider.model or (models[0] if models else None)
    if probe_model:
        probe_dims = _probe_embedding_dim(
            base_url=base_url,
            path=provider.resolved_http_embeddings_path,
            headers=headers,
            timeout=timeout,
            model=probe_model,
        )
        if probe_dims is not None:
            dims[probe_model] = probe_dims
            if probe_model not in models:
                models.append(probe_model)

    if not models and provider.model:
        models = [provider.model]
    if not dims and provider.resolved_hint_dim and models:
        dims[models[0]] = provider.resolved_hint_dim

    return DiscoveryResult(
        provider=provider.name,
        fetched_at=time.time(),
        models=tuple(models),
        dims=dims,
        source=source,
    )


def _extract_models(payload: Any) -> list[str]:
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    models: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        if identifier is None:
            continue
        models.append(str(identifier))
    return models


def _probe_embedding_dim(
    *,
    base_url: str,
    path: str,
    headers: dict[str, str],
    timeout: float,
    model: str,
) -> int | None:
    endpoint = f"{base_url}{path}"
    payload = {"input": ["ping"], "model": model}
    try:
        response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    data = body.get("data")
    if not isinstance(data, list) or not data:
        return None
    first = data[0] if isinstance(data[0], dict) else {}
    embedding = first.get("embedding")
    if not isinstance(embedding, list):
        return None
    return len(embedding)


def _to_result(provider: str, payload: dict[str, Any]) -> DiscoveryResult:
    raw_models = payload.get("models")
    models = tuple(str(item) for item in raw_models) if isinstance(raw_models, list) else ()
    raw_dims = payload.get("dims")
    dims = {str(k): int(v) for k, v in raw_dims.items()} if isinstance(raw_dims, dict) else {}
    return DiscoveryResult(
        provider=provider,
        fetched_at=float(payload.get("fetched_at") or 0.0),
        models=models,
        dims=dims,
        source=str(payload.get("source") or "cache"),
    )

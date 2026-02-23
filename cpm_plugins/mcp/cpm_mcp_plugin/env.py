"""Environment contract for MCP plugin runtime."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MCPSettings:
    cpm_root: Path
    registry: str | None
    embedding_url: str | None
    embedding_model: str | None
    embedding_mode: str


def load_settings(
    *,
    cpm_root: str | None = None,
    registry: str | None = None,
    embedding_url: str | None = None,
    embedding_model: str | None = None,
) -> MCPSettings:
    root_value = (
        cpm_root
        or os.environ.get("CPM_ROOT")
        or os.environ.get("RAG_CPM_DIR")
        or ".cpm"
    )
    reg_value = registry or os.environ.get("REGISTRY")
    embed_url = embedding_url or os.environ.get("EMBEDDING_URL") or os.environ.get("RAG_EMBED_URL")
    embed_model = embedding_model or os.environ.get("EMBEDDING_MODEL")
    embed_mode = os.environ.get("RAG_EMBED_MODE") or "http"
    return MCPSettings(
        cpm_root=Path(root_value),
        registry=reg_value,
        embedding_url=embed_url,
        embedding_model=embed_model,
        embedding_mode=embed_mode,
    )


def apply_settings_to_env(settings: MCPSettings) -> None:
    os.environ["CPM_ROOT"] = str(settings.cpm_root)
    os.environ["RAG_CPM_DIR"] = str(settings.cpm_root)
    if settings.registry:
        os.environ["REGISTRY"] = settings.registry
    if settings.embedding_url:
        os.environ["EMBEDDING_URL"] = settings.embedding_url
        os.environ["RAG_EMBED_URL"] = settings.embedding_url
    if settings.embedding_model:
        os.environ["EMBEDDING_MODEL"] = settings.embedding_model
    if settings.embedding_mode:
        os.environ["RAG_EMBED_MODE"] = settings.embedding_mode

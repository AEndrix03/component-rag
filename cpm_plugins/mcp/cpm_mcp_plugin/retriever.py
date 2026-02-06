"""Helper that performs FAISS retrieval for a context packet."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import faiss
from cpm_builtin.embeddings import EmbeddingClient

from .reader import PacketReader

DEFAULT_EMBED_URL = "http://127.0.0.1:8876"
DEFAULT_EMBED_MODE = "http"


class EmbedServerError(RuntimeError):
    """Raised when the embedding HTTP service is unreachable."""

    def __init__(self, embed_url: str, embed_mode: str) -> None:
        super().__init__(f"embedding server unreachable at {embed_url} (mode={embed_mode})")
        self.embed_url = embed_url
        self.embed_mode = embed_mode


class PacketRetriever:
    """Retrieve nearest neighbors from a built packet."""

    def __init__(
        self,
        cpm_dir: Path,
        packet: str,
        *,
        embed_url: Optional[str] = None,
        embed_mode: Optional[str] = None,
    ) -> None:
        self.cpm_dir = cpm_dir
        self.packet = packet
        self._reader = PacketReader(cpm_dir)
        self.packet_dir = self._reader.resolve_packet_dir(packet)
        if self.packet_dir is None:
            raise FileNotFoundError(packet)

        manifest_path = self.packet_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"missing manifest at {manifest_path}")

        self.manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        embedding_cfg = self.manifest.get("embedding") or {}
        self.model_name = str(embedding_cfg.get("model"))
        if not self.model_name:
            raise ValueError("manifest.embedding.model is required")
        self.max_seq_length = int(embedding_cfg.get("max_seq_length", 1024))
        self.embed_url = (
            embed_url
            or os.environ.get("RAG_EMBED_URL")
            or DEFAULT_EMBED_URL
        )
        self.embed_mode = (
            embed_mode
            or os.environ.get("RAG_EMBED_MODE")
            or DEFAULT_EMBED_MODE
        )
        self.docs = self._load_docs()
        self.index = self._load_index()

    def _load_docs(self) -> List[Dict[str, Any]]:
        docs_path = self.packet_dir / "docs.jsonl"
        if not docs_path.exists():
            raise FileNotFoundError(f"missing docs.jsonl at {docs_path}")
        entries: List[Dict[str, Any]] = []
        with docs_path.open("r", encoding="utf-8") as stream:
            for line in stream:
                payload = line.strip()
                if not payload:
                    continue
                entry = json.loads(payload)
                entries.append(entry)
        return entries

    def _load_index(self) -> faiss.Index:
        index_path = self.packet_dir / "faiss" / "index.faiss"
        if not index_path.exists():
            raise FileNotFoundError(f"missing faiss index at {index_path}")
        return faiss.read_index(str(index_path))

    def _new_embedder(self) -> EmbeddingClient:
        embedder = EmbeddingClient(self.embed_url, mode=self.embed_mode)
        if not embedder.health():
            raise EmbedServerError(self.embed_url, self.embed_mode)
        return embedder

    def retrieve(self, query: str, k: int) -> Dict[str, Any]:
        embedder = self._new_embedder()
        vector = embedder.embed_texts(
            [query],
            model_name=self.model_name,
            max_seq_length=self.max_seq_length,
            normalize=True,
            dtype="float32",
            show_progress=False,
        )
        scores, ids = self.index.search(vector, int(k))
        scores, ids = scores[0], ids[0]

        hits: List[Dict[str, Any]] = []
        for idx, score in zip(ids, scores):
            if int(idx) < 0:
                continue
            doc = self.docs[int(idx)]
            hits.append(
                {
                    "score": float(score),
                    "id": doc.get("id"),
                    "text": doc.get("text"),
                    "metadata": doc.get("metadata") or {},
                }
            )

        return {
            "ok": True,
            "packet": self.packet_dir.name,
            "packet_path": str(self.packet_dir).replace("\\", "/"),
            "query": query,
            "k": int(k),
            "embedding": {
                "model": self.model_name,
                "max_seq_length": self.max_seq_length,
                "embed_url": self.embed_url,
                "mode": self.embed_mode,
            },
            "results": hits,
        }

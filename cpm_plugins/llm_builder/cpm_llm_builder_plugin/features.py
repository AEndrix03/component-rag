"""Builder plugin with deterministic pre-chunk + LLM enrichment pipeline."""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np
import yaml
from cpm_builtin.embeddings import EmbeddingClient
from cpm_core.api import CPMAbstractBuilder, cpmbuilder
from cpm_core.build.builder import (
    CODE_EXTS,
    DEFAULT_EMBED_URL,
    DEFAULT_MODEL,
    TEXT_EXTS,
    _archive_packet_dir,
    _chunk_hash,
    _infer_tags,
    _load_existing_cache,
    _read_text_file,
    _write_cpm_yml,
)
from cpm_core.packet.faiss_db import FaissFlatIP
from cpm_core.packet.io import compute_checksums, write_docs_jsonl, write_manifest, write_vectors_f16
from cpm_core.packet.models import DocChunk, EmbeddingSpec, PacketManifest

from .cache import CacheV2, FileCacheEntry, load_cache, save_cache
from .classifiers import classify_file
from .llm_client import LLMClient, LLMClientConfig
from .postprocess import apply_chunk_constraints
from .prechunk import prechunk
from .schemas import Chunk, ChunkConstraints, SourceDocument, segment_cache_key
from .validators import validate_chunks

SUPPORTED_EXTS = CODE_EXTS | TEXT_EXTS | {".md", ".markdown", ".html", ".htm", ".json", ".yaml", ".yml"}
DEFAULT_CONFIG_NAME = "config.yml"
CHUNK_CACHE_NAME = "chunk_cache.json"

_PLUGIN_ROOT: Path | None = None


def set_plugin_root(path: Path) -> None:
    global _PLUGIN_ROOT
    _PLUGIN_ROOT = path


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolve_config_path(config_arg: str | None) -> Path:
    if config_arg:
        return Path(config_arg).expanduser().resolve()
    if _PLUGIN_ROOT is not None:
        return (_PLUGIN_ROOT / DEFAULT_CONFIG_NAME).resolve()
    return Path(DEFAULT_CONFIG_NAME).resolve()


@dataclass(frozen=True)
class LLMBuilderPluginConfig:
    llm_endpoint: str
    request_timeout: float = 30.0
    llm_model: str = "chunker-xxx"
    prompt_version: str = "chunk_enrich_v1"
    api_style: str = "auto"
    max_retries: int = 2
    max_chunk_tokens: int = 800
    min_chunk_tokens: int = 120
    max_segments_per_request: int = 8

    @classmethod
    def from_path(cls, path: Path) -> "LLMBuilderPluginConfig":
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ValueError("config.yml must contain a mapping")

        legacy_endpoint = str(payload.get("llm_endpoint") or "").strip()
        llm_cfg = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}
        endpoint = str(llm_cfg.get("endpoint") or legacy_endpoint).strip()
        if not endpoint:
            raise ValueError("config.yml must define llm.endpoint or llm_endpoint")

        constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}

        return cls(
            llm_endpoint=endpoint,
            request_timeout=float(payload.get("request_timeout", 30.0)),
            llm_model=str(llm_cfg.get("model") or "chunker-xxx"),
            prompt_version=str(llm_cfg.get("prompt_version") or "chunk_enrich_v1"),
            api_style=str(llm_cfg.get("api_style") or "auto"),
            max_retries=int(llm_cfg.get("max_retries", 2)),
            max_chunk_tokens=int(constraints.get("max_chunk_tokens", 800)),
            min_chunk_tokens=int(constraints.get("min_chunk_tokens", 120)),
            max_segments_per_request=int(constraints.get("max_segments_per_request", 8)),
        )


@dataclass(frozen=True)
class LLMBuilderRuntimeConfig:
    llm_endpoint: str
    request_timeout: float
    llm_model: str
    prompt_version: str
    api_style: str
    max_retries: int
    constraints: ChunkConstraints
    model_name: str
    max_seq_length: int
    version: str
    archive: bool
    archive_format: str
    embed_url: str
    embeddings_mode: str
    timeout: float | None


@cpmbuilder(name="cpm-llm-builder", group="llm")
class CPMLLMBuilder(CPMAbstractBuilder):
    def _log(self, stage: str, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        print(f"[llm-builder:{stage}:{ts}] {message}")

    @classmethod
    def configure(cls, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("source", help="Source directory to build")
        parser.add_argument("--destination", required=True, help="Destination packet directory")
        parser.add_argument("--packet-version", default="0.0.0", help="Packet version for manifest/cpm.yml")
        parser.add_argument("--config", help="Plugin config.yml path (default: plugin config.yml)")
        parser.add_argument("--llm-endpoint", help="Override LLM endpoint from config")
        parser.add_argument("--request-timeout", type=float, help="Timeout in seconds for LLM calls")
        parser.add_argument("--llm-model", help="Override LLM model")
        parser.add_argument("--prompt-version", help="Override prompt version")
        parser.add_argument(
            "--llm-api-style",
            choices=["auto", "responses", "chat_completions"],
            help="LLM API style; default auto",
        )
        parser.add_argument("--max-retries", type=int, help="LLM retries")
        parser.add_argument("--max-chunk-tokens", type=int, help="Chunk hard max size")
        parser.add_argument("--min-chunk-tokens", type=int, help="Chunk soft min size")
        parser.add_argument("--max-segments-per-request", type=int, help="LLM batch size")
        parser.add_argument("--model-name", default=DEFAULT_MODEL, help="Embedding model name")
        parser.add_argument("--max-seq-length", type=int, default=1024, help="Embedding max sequence length")
        parser.add_argument("--embed-url", default=DEFAULT_EMBED_URL, help="Embedding endpoint URL")
        parser.add_argument("--embeddings-mode", choices=["http", "legacy"], default="http")
        parser.add_argument("--timeout", type=float, default=None, help="Embedding request timeout in seconds")
        parser.add_argument("--archive", dest="archive", action="store_true", help="Create archive output")
        parser.add_argument("--no-archive", dest="archive", action="store_false", help="Skip archive output")
        parser.set_defaults(archive=True)
        parser.add_argument("--archive-format", choices=["tar.gz", "zip"], default="tar.gz")

    def __init__(self, config: LLMBuilderRuntimeConfig | None = None, *, embedder: Any | None = None) -> None:
        self.config = config
        self.embedder = embedder

    def run(self, argv: Sequence[str]) -> int:
        args = argv
        config_path = _resolve_config_path(getattr(args, "config", None))
        if not config_path.exists():
            print(f"[error] config file not found: {config_path}")
            return 1
        try:
            base = LLMBuilderPluginConfig.from_path(config_path)
        except Exception as exc:
            print(f"[error] invalid config.yml: {exc}")
            return 1

        constraints = ChunkConstraints(
            max_chunk_tokens=int(getattr(args, "max_chunk_tokens", None) or base.max_chunk_tokens),
            min_chunk_tokens=int(getattr(args, "min_chunk_tokens", None) or base.min_chunk_tokens),
            max_segments_per_request=int(
                getattr(args, "max_segments_per_request", None) or base.max_segments_per_request
            ),
        )

        runtime = LLMBuilderRuntimeConfig(
            llm_endpoint=str(getattr(args, "llm_endpoint", None) or base.llm_endpoint),
            request_timeout=float(getattr(args, "request_timeout", None) or base.request_timeout),
            llm_model=str(getattr(args, "llm_model", None) or base.llm_model),
            prompt_version=str(getattr(args, "prompt_version", None) or base.prompt_version),
            api_style=str(getattr(args, "llm_api_style", None) or base.api_style),
            max_retries=int(getattr(args, "max_retries", None) or base.max_retries),
            constraints=constraints,
            model_name=str(getattr(args, "model_name", None) or DEFAULT_MODEL),
            max_seq_length=int(getattr(args, "max_seq_length", None) or 1024),
            version=str(getattr(args, "packet_version", None) or "0.0.0"),
            archive=bool(getattr(args, "archive", True)),
            archive_format=str(getattr(args, "archive_format", None) or "tar.gz"),
            embed_url=str(getattr(args, "embed_url", None) or DEFAULT_EMBED_URL),
            embeddings_mode=str(getattr(args, "embeddings_mode", None) or "http"),
            timeout=getattr(args, "timeout", None),
        )
        self.config = runtime
        self.embedder = self.embedder or EmbeddingClient(
            base_url=runtime.embed_url,
            mode=runtime.embeddings_mode,
            timeout_s=runtime.timeout,
        )
        manifest = self.build(str(getattr(args, "source")), destination=str(getattr(args, "destination")))
        return 0 if manifest is not None else 1

    def _fallback_chunk(self, *, source: SourceDocument, segment_text: str, segment_id: str, start: int, end: int) -> Chunk:
        return Chunk(
            id=segment_id,
            text=segment_text,
            title="",
            summary="",
            tags=(),
            anchors={"path": source.path, "start_line": start, "end_line": end},
            relations={},
            metadata={"fallback": True},
        )

    def build(self, source: str, *, destination: str | None = None) -> PacketManifest | None:
        if self.config is None:
            raise ValueError("runtime config is not initialized")
        if self.embedder is None:
            self.embedder = EmbeddingClient(
                base_url=self.config.embed_url,
                mode=self.config.embeddings_mode,
                timeout_s=self.config.timeout,
            )

        source_path = Path(source).resolve()
        if not source_path.exists():
            print(f"[error] source '{source_path}' does not exist")
            return None
        if destination is None:
            raise ValueError("destination path must be provided")
        out_root = Path(destination).resolve()
        out_root.mkdir(parents=True, exist_ok=True)
        (out_root / "faiss").mkdir(parents=True, exist_ok=True)
        self._log("build", f"input_dir={source_path}")
        self._log("build", f"output_dir={out_root}")

        llm_client = LLMClient(
            LLMClientConfig(
                endpoint=self.config.llm_endpoint,
                model=self.config.llm_model,
                request_timeout=self.config.request_timeout,
                prompt_version=self.config.prompt_version,
                api_style=self.config.api_style,
                max_retries=self.config.max_retries,
                verbose=True,
            )
        )

        chunk_cache_path = out_root / CHUNK_CACHE_NAME
        cache = load_cache(chunk_cache_path)
        next_cache = CacheV2()
        next_cache.segment_enrichment.update(cache.segment_enrichment)

        chunks: list[DocChunk] = []
        ext_counts: dict[str, int] = {}
        files_indexed = 0
        llm_calls = 0
        file_cache_hits = 0
        segment_cache_hits = 0

        rel_root = source_path.resolve()
        for file_path in sorted(source_path.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SUPPORTED_EXTS:
                continue

            text = _read_text_file(file_path)
            if not text.strip():
                continue
            files_indexed += 1

            rel = str(file_path.resolve().relative_to(rel_root)).replace("\\", "/")
            ext = file_path.suffix.lower()
            ext_counts[ext] = ext_counts.get(ext, 0) + 1

            classification = classify_file(file_path, text)
            self._log(
                "classify",
                f"path={rel} pipeline={classification.pipeline} language={classification.language} mime={classification.mime}",
            )
            if not classification.is_supported_text:
                self._log("skip", f"path={rel} reason=unsupported_text")
                continue

            source_hash = _sha256_text(text)
            cached_file = cache.files.get(rel)
            if cached_file and cached_file.source_hash == source_hash:
                segments = cached_file.segments
                file_cache_hits += 1
                self._log("prechunk", f"path={rel} source_cache_hit segments={len(segments)}")
            else:
                segments = prechunk(rel, text, classification)
                self._log("prechunk", f"path={rel} source_cache_miss segments={len(segments)}")

            next_cache.files[rel] = FileCacheEntry(
                source_hash=source_hash,
                classification={
                    "pipeline": classification.pipeline,
                    "language": classification.language,
                    "mime": classification.mime,
                },
                segments=list(segments),
            )
            if not segments:
                continue

            source_doc = SourceDocument(
                path=rel,
                language=classification.language,
                mime=classification.mime,
                source_hash=source_hash,
            )

            resolved_chunks: list[Chunk] = []
            missing_segments = []
            missing_keys = []
            for segment in segments:
                key = segment_cache_key(
                    segment=segment,
                    model=self.config.llm_model,
                    prompt_version=self.config.prompt_version,
                    constraints=self.config.constraints,
                )
                cached = cache.segment_enrichment.get(key)
                if cached is not None:
                    resolved_chunks.append(cached)
                    segment_cache_hits += 1
                else:
                    missing_segments.append(segment)
                    missing_keys.append(key)
            self._log(
                "cache",
                f"path={rel} segments_total={len(segments)} segment_cache_hits={len(segments)-len(missing_segments)} "
                f"segment_cache_miss={len(missing_segments)}",
            )

            max_batch = max(1, self.config.constraints.max_segments_per_request)
            for start in range(0, len(missing_segments), max_batch):
                segment_batch = missing_segments[start : start + max_batch]
                key_batch = missing_keys[start : start + max_batch]
                self._log(
                    "llm",
                    f"path={rel} batch_start={start} batch_size={len(segment_batch)} model={self.config.llm_model}",
                )
                try:
                    enriched = llm_client.enrich(
                        source=source_doc,
                        segments=segment_batch,
                        constraints=self.config.constraints,
                    )
                    llm_calls += 1
                    self._log("llm", f"path={rel} batch_start={start} enriched={len(enriched)}")
                except Exception as exc:
                    print(f"[warn] llm enrichment failed for {rel}: {exc}; fallback enabled")
                    enriched = [
                        self._fallback_chunk(
                            source=source_doc,
                            segment_text=segment.text,
                            segment_id=segment.id,
                            start=segment.start_line,
                            end=segment.end_line,
                        )
                        for segment in segment_batch
                    ]
                for key, enriched_chunk in zip(key_batch, enriched):
                    next_cache.segment_enrichment[key] = enriched_chunk
                    resolved_chunks.append(enriched_chunk)

            post = apply_chunk_constraints(resolved_chunks, self.config.constraints)
            self._log(
                "postprocess",
                f"path={rel} before={len(resolved_chunks)} after={len(post)} "
                f"max_tokens={self.config.constraints.max_chunk_tokens} min_tokens={self.config.constraints.min_chunk_tokens}",
            )
            validation = validate_chunks(post)
            for warning in validation.warnings:
                print(f"[warn] {rel}: {warning}")

            for chunk in validation.chunks:
                meta = dict(chunk.metadata)
                meta.update(
                    {
                        "path": rel,
                        "ext": ext,
                        "title": chunk.title,
                        "summary": chunk.summary,
                        "tags": list(chunk.tags),
                        "anchors": dict(chunk.anchors),
                        "relations": dict(chunk.relations),
                    }
                )
                chunks.append(DocChunk(id=chunk.id, text=chunk.text, metadata=meta))
            self._log("chunks", f"path={rel} final_chunks={len(validation.chunks)}")

        save_cache(chunk_cache_path, next_cache)
        self._log("scan", f"files_indexed={files_indexed}")
        self._log("scan", f"chunks_total={len(chunks)}")
        self._log(
            "scan",
            f"llm_calls={llm_calls} file_cache_hits={file_cache_hits} segment_cache_hits={segment_cache_hits}",
        )
        if not chunks:
            print("[error] No chunks found.")
            return None

        cache_pack = _load_existing_cache(
            out_root,
            model_name=self.config.model_name,
            max_seq_length=self.config.max_seq_length,
        )
        cache_vecs: dict[str, np.ndarray] = {}
        cache_dim: Optional[int] = None
        if cache_pack:
            cache_vecs, cache_dim = cache_pack
            self._log("embed-cache", f"enabled cached_vectors={len(cache_vecs)} dim={cache_dim}")
        else:
            self._log("embed-cache", "disabled no compatible previous build found")

        new_hashes = [_chunk_hash(chunk.text) for chunk in chunks]
        prev_set = set(cache_vecs.keys())
        new_set = set(new_hashes)
        removed = len(prev_set - new_set) if cache_vecs else 0
        reused = sum(1 for hsh in new_hashes if hsh in cache_vecs)

        to_embed_idx: list[int] = []
        to_embed_texts: list[str] = []
        for idx, hsh in enumerate(new_hashes):
            if hsh not in cache_vecs:
                to_embed_idx.append(idx)
                to_embed_texts.append(chunks[idx].text)
        self._log(
            "embed-cache",
            f"new_chunks={len(chunks)} reused={reused} to_embed={len(to_embed_idx)} removed={removed}",
        )

        if not self.embedder.health():
            print(
                f"[error] embedding server not reachable at {self.config.embed_url} (mode={self.config.embeddings_mode})"
            )
            return None

        vec_missing: Optional[np.ndarray] = None
        dim: Optional[int] = cache_dim
        if to_embed_texts:
            vec_missing = self.embedder.embed_texts(
                to_embed_texts,
                model_name=self.config.model_name,
                max_seq_length=self.config.max_seq_length,
                normalize=True,
                dtype="float32",
                show_progress=True,
            )
            dim = int(vec_missing.shape[1])
        elif dim is None and chunks:
            vec_missing = self.embedder.embed_texts(
                [chunks[0].text],
                model_name=self.config.model_name,
                max_seq_length=self.config.max_seq_length,
                normalize=True,
                dtype="float32",
                show_progress=False,
            )
            dim = int(vec_missing.shape[1])
            to_embed_idx = [0]
        assert dim is not None

        if cache_dim is not None and cache_dim != dim:
            cache_vecs = {}
            reused = 0
            to_embed_idx = list(range(len(chunks)))
            to_embed_texts = [chunk.text for chunk in chunks]
            vec_missing = self.embedder.embed_texts(
                to_embed_texts,
                model_name=self.config.model_name,
                max_seq_length=self.config.max_seq_length,
                normalize=True,
                dtype="float32",
                show_progress=True,
            )
            dim = int(vec_missing.shape[1])

        final_vecs = np.empty((len(chunks), dim), dtype=np.float32)
        if cache_vecs:
            for idx, hsh in enumerate(new_hashes):
                vector = cache_vecs.get(hsh)
                if vector is not None:
                    final_vecs[idx] = vector
        if to_embed_idx:
            assert vec_missing is not None
            for miss_idx, chunk_idx in enumerate(to_embed_idx):
                final_vecs[chunk_idx] = vec_missing[miss_idx]

        docs_path = out_root / "docs.jsonl"
        write_docs_jsonl(chunks, docs_path)
        self._log("write", f"docs_jsonl={docs_path} lines={len(chunks)}")
        db = FaissFlatIP(dim=dim)
        db.add(final_vecs)
        db_path = out_root / "faiss" / "index.faiss"
        db.save(str(db_path))
        self._log("write", f"faiss_index={db_path} ntotal={db.index.ntotal}")
        vectors_path = out_root / "vectors.f16.bin"
        write_vectors_f16(final_vecs, vectors_path)
        self._log("write", f"vectors={vectors_path} shape={final_vecs.shape}")

        tags = _infer_tags(ext_counts)
        _write_cpm_yml(
            out_root,
            name=out_root.name,
            version=self.config.version,
            description=source_path.as_posix(),
            tags=tags,
            entrypoints=["query"],
            embedding_model=self.config.model_name,
            embedding_dim=dim,
            embedding_normalized=True,
        )

        manifest = PacketManifest(
            schema_version="1.0",
            packet_id=out_root.name,
            embedding=EmbeddingSpec(
                provider="sentence-transformers",
                model=self.config.model_name,
                dim=dim,
                dtype="float16",
                normalized=True,
                max_seq_length=self.config.max_seq_length,
            ),
            similarity={
                "space": "cosine",
                "index_type": "faiss.IndexFlatIP",
                "notes": "cosine via inner product on normalized vectors",
            },
            files={
                "docs": "docs.jsonl",
                "vectors": {"path": "vectors.f16.bin", "format": "f16_rowmajor"},
                "index": {"path": "faiss/index.faiss", "format": "faiss"},
                "chunk_cache": CHUNK_CACHE_NAME,
                "calibration": None,
            },
            counts={"docs": len(chunks), "vectors": int(db.index.ntotal)},
            source={"input_dir": source_path.as_posix(), "file_ext_counts": ext_counts},
            cpm={
                "name": out_root.name,
                "version": self.config.version,
                "tags": tags,
                "entrypoints": ["query"],
            },
            incremental={
                "enabled": bool(cache_pack or cache.files),
                "reused": reused,
                "embedded": len(to_embed_idx),
                "removed": removed,
                "file_cache_hits": file_cache_hits,
                "segment_cache_hits": segment_cache_hits,
                "llm_calls": llm_calls,
            },
        )
        manifest.checksums = compute_checksums(
            out_root,
            ["cpm.yml", "docs.jsonl", "vectors.f16.bin", "faiss/index.faiss", CHUNK_CACHE_NAME],
        )
        manifest_path = out_root / "manifest.json"
        write_manifest(manifest, manifest_path)
        self._log("write", f"manifest={manifest_path}")

        if self.config.archive:
            archive_path = _archive_packet_dir(out_root, self.config.archive_format)
            self._log("write", f"archive={archive_path}")
        self._log("done", "build ok")
        return manifest

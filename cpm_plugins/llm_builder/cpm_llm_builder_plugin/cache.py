"""Chunk cache v2: file-level prechunk + segment enrichment cache."""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Mapping

from .schemas import Chunk, Segment


CACHE_VERSION = 2


@dataclass
class FileCacheEntry:
    source_hash: str
    classification: dict[str, Any] = field(default_factory=dict)
    segments: list[Segment] = field(default_factory=list)


@dataclass
class CacheV2:
    files: dict[str, FileCacheEntry] = field(default_factory=dict)
    segment_enrichment: dict[str, Chunk] = field(default_factory=dict)


def load_cache(path: Path) -> CacheV2:
    if not path.exists():
        return CacheV2()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return CacheV2()

    if isinstance(payload, Mapping) and payload.get("version") == CACHE_VERSION:
        return _load_v2(payload)

    # v1 migration: {"files": {"path": {"source_hash": "...", "chunks":[...]}}}
    migrated = CacheV2()
    files_raw = payload.get("files") if isinstance(payload, Mapping) else None
    if isinstance(files_raw, Mapping):
        for rel, entry in files_raw.items():
            if not isinstance(rel, str) or not isinstance(entry, Mapping):
                continue
            source_hash = entry.get("source_hash")
            chunks = entry.get("chunks")
            if not isinstance(source_hash, str):
                continue
            segments: list[Segment] = []
            if isinstance(chunks, list):
                for idx, item in enumerate(chunks):
                    if not isinstance(item, str):
                        continue
                    text = item.strip()
                    if not text:
                        continue
                    segments.append(
                        Segment(
                            id=f"{rel}:legacy:{idx}",
                            kind="legacy_chunk",
                            text=text,
                            start_line=1,
                            end_line=1,
                            metadata={},
                        )
                    )
            migrated.files[rel] = FileCacheEntry(
                source_hash=source_hash,
                classification={"pipeline": "legacy"},
                segments=segments,
            )
    return migrated


def _load_v2(payload: Mapping[str, Any]) -> CacheV2:
    result = CacheV2()
    files_raw = payload.get("files")
    if isinstance(files_raw, Mapping):
        for rel, value in files_raw.items():
            if not isinstance(rel, str) or not isinstance(value, Mapping):
                continue
            source_hash = value.get("source_hash")
            if not isinstance(source_hash, str):
                continue
            cls = dict(value.get("classification") or {})
            seg_payload = value.get("segments") or []
            segments = []
            if isinstance(seg_payload, list):
                for item in seg_payload:
                    if isinstance(item, Mapping):
                        try:
                            segments.append(Segment.from_dict(item))
                        except Exception:
                            continue
            result.files[rel] = FileCacheEntry(
                source_hash=source_hash,
                classification=cls,
                segments=segments,
            )

    seg_enrichment = payload.get("segment_enrichment")
    if isinstance(seg_enrichment, Mapping):
        for key, value in seg_enrichment.items():
            if not isinstance(key, str) or not isinstance(value, Mapping):
                continue
            try:
                result.segment_enrichment[key] = Chunk.from_dict(value)
            except Exception:
                continue
    return result


def save_cache(path: Path, cache: CacheV2) -> None:
    payload = {
        "version": CACHE_VERSION,
        "files": {
            rel: {
                "source_hash": entry.source_hash,
                "classification": dict(entry.classification),
                "segments": [segment.to_dict() for segment in entry.segments],
            }
            for rel, entry in sorted(cache.files.items())
        },
        "segment_enrichment": {
            key: value.to_dict()
            for key, value in sorted(cache.segment_enrichment.items())
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


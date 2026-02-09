"""Validation and quality gates for final chunks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .schemas import Chunk


@dataclass(frozen=True)
class ValidationResult:
    chunks: tuple[Chunk, ...]
    warnings: tuple[str, ...]


def validate_chunks(chunks: Sequence[Chunk]) -> ValidationResult:
    warnings: list[str] = []
    seen: set[str] = set()
    valid: list[Chunk] = []

    for chunk in chunks:
        if not chunk.text.strip():
            warnings.append(f"chunk {chunk.id!r} dropped: empty text")
            continue
        if not chunk.id:
            warnings.append("chunk dropped: missing id")
            continue
        if chunk.id in seen:
            warnings.append(f"chunk {chunk.id!r} dropped: duplicate id")
            continue
        seen.add(chunk.id)
        anchors = dict(chunk.anchors)
        if "path" not in anchors:
            warnings.append(f"chunk {chunk.id!r} has no anchors.path")
        if not chunk.summary:
            warnings.append(f"chunk {chunk.id!r} has empty summary")
        if not chunk.tags:
            warnings.append(f"chunk {chunk.id!r} has empty tags")
        valid.append(chunk)

    return ValidationResult(chunks=tuple(valid), warnings=tuple(warnings))


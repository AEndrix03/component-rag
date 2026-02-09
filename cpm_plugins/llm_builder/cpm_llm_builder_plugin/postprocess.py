"""Post-processing rules for chunk size constraints."""

from __future__ import annotations

from typing import Sequence

from .schemas import Chunk, ChunkConstraints, estimate_tokens


def _split_chunk(chunk: Chunk, max_tokens: int) -> list[Chunk]:
    lines = chunk.text.splitlines()
    if not lines:
        return [chunk]
    result: list[Chunk] = []
    buffer: list[str] = []
    part = 0
    for line in lines:
        candidate = "\n".join(buffer + [line]).strip()
        if buffer and estimate_tokens(candidate) > max_tokens:
            text = "\n".join(buffer).strip()
            if text:
                result.append(
                    Chunk(
                        id=f"{chunk.id}:part:{part}",
                        text=text,
                        title=chunk.title,
                        summary=chunk.summary,
                        tags=chunk.tags,
                        anchors=dict(chunk.anchors),
                        relations=dict(chunk.relations),
                        metadata=dict(chunk.metadata),
                    )
                )
                part += 1
            buffer = [line]
        else:
            buffer.append(line)
    final_text = "\n".join(buffer).strip()
    if final_text:
        result.append(
            Chunk(
                id=f"{chunk.id}:part:{part}" if part else chunk.id,
                text=final_text,
                title=chunk.title,
                summary=chunk.summary,
                tags=chunk.tags,
                anchors=dict(chunk.anchors),
                relations=dict(chunk.relations),
                metadata=dict(chunk.metadata),
            )
        )
    return result or [chunk]


def _merge_small_chunks(chunks: Sequence[Chunk], min_tokens: int) -> list[Chunk]:
    if not chunks:
        return []
    merged: list[Chunk] = []
    buffer: Chunk | None = None
    for chunk in chunks:
        if buffer is None:
            buffer = chunk
            continue
        if estimate_tokens(buffer.text) >= min_tokens:
            merged.append(buffer)
            buffer = chunk
            continue
        combined = f"{buffer.text}\n\n{chunk.text}".strip()
        buffer = Chunk(
            id=f"{buffer.id}+{chunk.id}",
            text=combined,
            title=buffer.title or chunk.title,
            summary=buffer.summary or chunk.summary,
            tags=tuple(sorted(set((*buffer.tags, *chunk.tags)))),
            anchors=dict(buffer.anchors),
            relations=dict(buffer.relations),
            metadata=dict(buffer.metadata),
        )
    if buffer is not None:
        merged.append(buffer)
    return merged


def apply_chunk_constraints(chunks: Sequence[Chunk], constraints: ChunkConstraints) -> list[Chunk]:
    split_done: list[Chunk] = []
    for chunk in chunks:
        if estimate_tokens(chunk.text) > constraints.max_chunk_tokens:
            split_done.extend(_split_chunk(chunk, constraints.max_chunk_tokens))
        else:
            split_done.append(chunk)
    return _merge_small_chunks(split_done, constraints.min_chunk_tokens)


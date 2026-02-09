"""HTTP client for OpenAI-like enrichment endpoint with legacy compatibility."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import random
import re
import time
from typing import Any, Mapping, Sequence
import json
import uuid

import requests

from .schemas import Chunk, ChunkConstraints, Segment, SourceDocument, normalize_chunk_list


@dataclass(frozen=True)
class LLMClientConfig:
    endpoint: str
    model: str
    request_timeout: float
    prompt_version: str
    api_style: str = "auto"
    max_retries: int = 2
    retry_backoff_seconds: float = 0.5
    verbose: bool = True


def _prompt_text(prompt_version: str) -> str:
    return (
        f"prompt={prompt_version}. "
        "Return ONLY valid JSON object with key 'chunks'. "
        "For each input segment include: id,title,summary,tags,anchors,text,relations."
    )


def _build_openai_like_payload(
    *,
    source: SourceDocument,
    segments: Sequence[Segment],
    constraints: ChunkConstraints,
    model: str,
    prompt_version: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _prompt_text(prompt_version)},
                    {
                        "type": "input_json",
                        "json": {
                            "task": "chunk.enrich",
                            "source": {
                                "path": source.path,
                                "language": source.language,
                                "mime": source.mime,
                                "hash": source.source_hash,
                            },
                            "segments": [segment.to_dict() for segment in segments],
                            "constraints": constraints.to_dict(),
                        },
                    },
                ],
            }
        ],
        "metadata": {
            "cpm_plugin": "cpm-llm-builder",
            "prompt_version": prompt_version,
        },
    }


def _build_chat_completions_payload(
    *,
    source: SourceDocument,
    segments: Sequence[Segment],
    constraints: ChunkConstraints,
    model: str,
    prompt_version: str,
) -> dict[str, Any]:
    task_payload = {
        "task": "chunk.enrich",
        "source": {
            "path": source.path,
            "language": source.language,
            "mime": source.mime,
            "hash": source.source_hash,
        },
        "segments": [segment.to_dict() for segment in segments],
        "constraints": constraints.to_dict(),
    }
    compact_user_payload = json.dumps(task_payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    _prompt_text(prompt_version)
                    + " Answer ONLY with valid JSON object containing key 'chunks'."
                ),
            },
            {
                "role": "user",
                "content": compact_user_payload,
            },
        ],
        "temperature": 0,
        "stream": False,
    }


def _preferred_styles(endpoint: str, api_style: str) -> list[str]:
    style = api_style.strip().lower()
    if style in {"responses", "chat_completions"}:
        return [style]
    endpoint_lower = endpoint.lower()
    if "chat/completions" in endpoint_lower:
        return ["chat_completions", "responses"]
    return ["responses", "chat_completions"]


def _extract_json_from_text(content: str) -> Any:
    raw = content.strip()
    if not raw:
        raise ValueError("empty LLM content")
    try:
        return json.loads(raw)
    except Exception:
        pass

    fenced = re.findall(r"```(?:json)?\s*(.*?)```", raw, flags=re.DOTALL | re.IGNORECASE)
    for candidate in fenced:
        candidate = candidate.strip()
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except Exception:
            continue

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        snippet = raw[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            pass
    raise ValueError("unable to parse JSON from LLM chat response")


def _compact_len(value: Any) -> int:
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    except Exception:
        return len(str(value))


def _payload_sizes(payload: Mapping[str, Any], style: str) -> tuple[int, int]:
    payload_chars = _compact_len(payload)
    prompt_chars = 0
    if style == "chat_completions":
        messages = payload.get("messages")
        if isinstance(messages, Sequence):
            for msg in messages:
                if isinstance(msg, Mapping):
                    prompt_chars += _compact_len(msg.get("content"))
    else:
        inputs = payload.get("input")
        if isinstance(inputs, Sequence):
            for item in inputs:
                if not isinstance(item, Mapping):
                    continue
                content = item.get("content")
                if isinstance(content, Sequence):
                    for block in content:
                        if not isinstance(block, Mapping):
                            continue
                        prompt_chars += _compact_len(block.get("text"))
                        prompt_chars += _compact_len(block.get("json"))
    return prompt_chars, payload_chars


class LLMClient:
    def __init__(self, config: LLMClientConfig) -> None:
        self.config = config

    def _log(self, message: str) -> None:
        if not self.config.verbose:
            return
        ts = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        print(f"[llm:{ts}] {message}")

    def enrich(
        self,
        *,
        source: SourceDocument,
        segments: Sequence[Segment],
        constraints: ChunkConstraints,
    ) -> list[Chunk]:
        if not segments:
            return []
        styles = _preferred_styles(self.config.endpoint, self.config.api_style)
        request_id = uuid.uuid4().hex[:12]
        self._log(
            f"request_id={request_id} source={source.path} segments={len(segments)} "
            f"styles={styles} model={self.config.model}"
        )
        last_exc: Exception | None = None
        for style in styles:
            payload = (
                _build_chat_completions_payload(
                    source=source,
                    segments=segments,
                    constraints=constraints,
                    model=self.config.model,
                    prompt_version=self.config.prompt_version,
                )
                if style == "chat_completions"
                else _build_openai_like_payload(
                    source=source,
                    segments=segments,
                    constraints=constraints,
                    model=self.config.model,
                    prompt_version=self.config.prompt_version,
                )
            )
            prompt_chars, payload_chars = _payload_sizes(payload, style)
            self._log(
                f"request_id={request_id} style={style} prompt_chars={prompt_chars} payload_chars={payload_chars}"
            )
            for attempt in range(self.config.max_retries + 1):
                try:
                    self._log(
                        f"request_id={request_id} style={style} attempt={attempt + 1} "
                        f"endpoint={self.config.endpoint}"
                    )
                    response = requests.post(
                        self.config.endpoint,
                        json=payload,
                        timeout=self.config.request_timeout,
                    )
                    response.raise_for_status()
                    self._log(
                        f"request_id={request_id} style={style} status={response.status_code} "
                        f"bytes={len(response.text)}"
                    )
                    return self._normalize_response(
                        response.json(),
                        segments=segments,
                        source=source,
                        style=style,
                    )
                except Exception as exc:
                    last_exc = exc
                    self._log(
                        f"request_id={request_id} style={style} attempt={attempt + 1} error={exc}"
                    )
                    if isinstance(exc, ValueError):
                        # Parsing/schema errors are usually deterministic for the same response;
                        # avoid wasting long retries on slow models.
                        break
                    if attempt >= self.config.max_retries:
                        break
                    base = self.config.retry_backoff_seconds * (2**attempt)
                    jitter = random.uniform(0.0, 0.25)
                    time.sleep(base + jitter)
        assert last_exc is not None
        raise last_exc

    def _normalize_response(
        self,
        payload: Any,
        *,
        segments: Sequence[Segment],
        source: SourceDocument,
        style: str,
    ) -> list[Chunk]:
        parsed_payload = payload
        if style == "chat_completions":
            parsed_payload = self._parse_chat_completions_payload(payload)
        chunks = normalize_chunk_list(parsed_payload)
        if not chunks:
            raise ValueError("empty chunks in response")
        self._log(f"normalized_chunks={len(chunks)} style={style} source={source.path}")
        return _ensure_chunk_defaults(chunks, segments=segments, source=source)

    @staticmethod
    def _parse_chat_completions_payload(payload: Any) -> Any:
        if not isinstance(payload, Mapping):
            raise ValueError("chat completions response must be an object")
        choices = payload.get("choices")
        if not isinstance(choices, Sequence) or not choices:
            raise ValueError("chat completions response has no choices")
        first = choices[0]
        if not isinstance(first, Mapping):
            raise ValueError("invalid chat completions choice")
        message = first.get("message")
        if not isinstance(message, Mapping):
            raise ValueError("chat completions choice has no message")
        content = message.get("content")
        if isinstance(content, str):
            return _extract_json_from_text(content)
        if isinstance(content, Sequence):
            parts: list[str] = []
            for item in content:
                if isinstance(item, Mapping):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return _extract_json_from_text("\n".join(parts))
        raise ValueError("chat completions message content is unsupported")


def _ensure_chunk_defaults(chunks: Sequence[Chunk], *, segments: Sequence[Segment], source: SourceDocument) -> list[Chunk]:
    index: dict[str, Segment] = {segment.id: segment for segment in segments}
    resolved: list[Chunk] = []
    for pos, chunk in enumerate(chunks):
        segment = index.get(chunk.id) if chunk.id else None
        if segment is None and pos < len(segments):
            segment = segments[pos]
        chunk_id = chunk.id or (segment.id if segment else f"{source.path}:chunk:{pos}")
        anchors = dict(chunk.anchors)
        if "path" not in anchors:
            anchors["path"] = source.path
        if segment is not None:
            anchors.setdefault("start_line", segment.start_line)
            anchors.setdefault("end_line", segment.end_line)
        text = chunk.text.strip() or (segment.text if segment else "")
        summary = chunk.summary.strip()
        if not summary:
            summary = _default_summary(text)
        tags = chunk.tags
        if not tags:
            tags = _default_tags(source=source, segment=segment)
        resolved.append(
            Chunk(
                id=chunk_id,
                text=text,
                title=chunk.title,
                summary=summary,
                tags=tags,
                anchors=anchors,
                relations=dict(chunk.relations),
                metadata=dict(chunk.metadata),
            )
        )
    return resolved


def _default_summary(text: str, *, limit: int = 180) -> str:
    compact = " ".join(text.strip().split())
    if not compact:
        return ""
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _default_tags(*, source: SourceDocument, segment: Segment | None) -> tuple[str, ...]:
    tags: list[str] = []
    if source.language:
        tags.append(source.language.lower())
    if segment is not None and segment.kind:
        tags.append(segment.kind.lower())
    if source.mime:
        mime_tail = source.mime.split("/")[-1].strip().lower()
        if mime_tail and mime_tail not in tags:
            tags.append(mime_tail)
    return tuple(tags[:5])

"""Deterministic pre-chunking for code and documents."""

from __future__ import annotations

import json
import re
from typing import Iterable

import yaml

from .classifiers import FileClassification
from .schemas import Segment, stable_hash


JAVA_TYPE_RE = re.compile(r"^\s*(public\s+|private\s+|protected\s+)?(class|interface|enum)\s+(\w+)")
JAVA_METHOD_RE = re.compile(
    r"^\s*(public|private|protected)?\s*(static\s+)?[\w<>\[\], ?]+\s+(\w+)\s*\([^)]*\)\s*\{?\s*$"
)
GENERIC_DEF_RE = re.compile(r"^\s*(def|class|function|fn|interface|type)\s+([A-Za-z_]\w*)")
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


def _make_id(path: str, kind: str, start_line: int, text: str) -> str:
    return f"{path}:{kind}:{start_line}:{stable_hash(text)[:10]}"


def _segment(path: str, kind: str, text: str, start: int, end: int, symbol: str | None = None) -> Segment:
    return Segment(
        id=_make_id(path, kind, start, text),
        kind=kind,
        text=text.strip(),
        start_line=start,
        end_line=end,
        symbol=symbol,
        metadata={},
    )


def _split_by_ranges(lines: list[str], ranges: Iterable[tuple[str, int, int, str | None]], path: str) -> list[Segment]:
    segments: list[Segment] = []
    for kind, start, end, symbol in ranges:
        start_idx = max(start - 1, 0)
        end_idx = min(end, len(lines))
        text = "\n".join(lines[start_idx:end_idx]).strip()
        if not text:
            continue
        segments.append(_segment(path, kind, text, start, end, symbol))
    return segments


def _java_segments(path: str, content: str) -> list[Segment]:
    lines = content.splitlines()
    if not lines:
        return []

    ranges: list[tuple[str, int, int, str | None]] = []
    current_start: int | None = None
    current_kind = "java_block"
    current_symbol: str | None = None
    brace_depth = 0

    for idx, line in enumerate(lines, start=1):
        type_match = JAVA_TYPE_RE.match(line)
        method_match = JAVA_METHOD_RE.match(line)
        starts_symbol = type_match is not None or method_match is not None

        if starts_symbol and current_start is None:
            current_start = idx
            if type_match is not None:
                current_kind = "class_header"
                current_symbol = type_match.group(3)
            else:
                current_kind = "method"
                current_symbol = method_match.group(3) if method_match else None

        brace_depth += line.count("{")
        brace_depth -= line.count("}")

        if current_start is not None and brace_depth <= 0:
            ranges.append((current_kind, current_start, idx, current_symbol))
            current_start = None
            current_kind = "java_block"
            current_symbol = None
            brace_depth = 0

    if current_start is not None:
        ranges.append((current_kind, current_start, len(lines), current_symbol))

    if not ranges:
        ranges.append(("java_file", 1, len(lines), None))
    return _split_by_ranges(lines, ranges, path)


def _generic_code_segments(path: str, content: str) -> list[Segment]:
    lines = content.splitlines()
    if not lines:
        return []
    starts: list[tuple[int, str | None]] = []
    for idx, line in enumerate(lines, start=1):
        match = GENERIC_DEF_RE.match(line)
        if match:
            starts.append((idx, match.group(2)))
    if not starts:
        return [_segment(path, "code_block", content, 1, len(lines), None)]

    ranges: list[tuple[str, int, int, str | None]] = []
    for pos, (start, symbol) in enumerate(starts):
        next_start = starts[pos + 1][0] if pos + 1 < len(starts) else len(lines) + 1
        ranges.append(("code_symbol", start, next_start - 1, symbol))
    return _split_by_ranges(lines, ranges, path)


def _markdown_segments(path: str, content: str) -> list[Segment]:
    lines = content.splitlines()
    if not lines:
        return []
    headings: list[tuple[int, str]] = []
    for idx, line in enumerate(lines, start=1):
        match = HEADING_RE.match(line)
        if match:
            headings.append((idx, match.group(2).strip()))
    if not headings:
        return [_segment(path, "markdown_section", content, 1, len(lines), None)]
    ranges: list[tuple[str, int, int, str | None]] = []
    for pos, (start, title) in enumerate(headings):
        next_start = headings[pos + 1][0] if pos + 1 < len(headings) else len(lines) + 1
        ranges.append(("heading_section", start, next_start - 1, title))
    return _split_by_ranges(lines, ranges, path)


def _json_yaml_segments(path: str, content: str, *, is_yaml: bool) -> list[Segment]:
    try:
        parsed = yaml.safe_load(content) if is_yaml else json.loads(content)
    except Exception:
        return [_segment(path, "structured_blob", content, 1, max(len(content.splitlines()), 1), None)]
    lines = content.splitlines()
    if not isinstance(parsed, dict):
        return [_segment(path, "structured_blob", content, 1, max(len(lines), 1), None)]
    if not lines:
        return []
    segments: list[Segment] = []
    for key, value in parsed.items():
        value_text = json.dumps(value, ensure_ascii=False, indent=2) if not is_yaml else yaml.safe_dump(value)
        text = f"{key}:\n{value_text}".strip()
        segments.append(_segment(path, "top_level_key", text, 1, len(lines), str(key)))
    return segments


def _text_segments(path: str, content: str) -> list[Segment]:
    parts = [part.strip() for part in re.split(r"\n\s*\n", content) if part.strip()]
    if not parts:
        return []
    lines = content.splitlines()
    segments: list[Segment] = []
    cursor = 1
    for idx, part in enumerate(parts):
        part_lines = part.splitlines()
        line_count = max(len(part_lines), 1)
        start = cursor
        end = min(cursor + line_count - 1, max(len(lines), 1))
        cursor = end + 1
        segments.append(_segment(path, "paragraph", part, start, end, f"paragraph_{idx+1}"))
    return segments


def prechunk(path: str, content: str, classification: FileClassification) -> list[Segment]:
    pipeline = classification.pipeline
    if pipeline == "java":
        return _java_segments(path, content)
    if pipeline == "code_generic":
        return _generic_code_segments(path, content)
    if pipeline in {"markdown", "html"}:
        return _markdown_segments(path, content)
    if pipeline == "json":
        return _json_yaml_segments(path, content, is_yaml=False)
    if pipeline == "yaml":
        return _json_yaml_segments(path, content, is_yaml=True)
    return _text_segments(path, content)

